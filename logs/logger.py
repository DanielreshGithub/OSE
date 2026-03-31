"""
StructuredLogger — SQLite-backed logging for OSE simulation runs.

Every decision, reasoning trace, world state snapshot, and event is written
to SQLite. The schema is designed for full replay: re-feeding a stored
system_prompt + perception_block with temperature=0 should reproduce the
same action.

Tables:
  runs         — one row per simulation run (metadata)
  decisions    — one row per actor decision per turn (full prompt + LLM output)
  turn_logs    — one row per turn (summary + world state snapshot)
  events       — one row per GlobalEvent (injected, actor, cascade)

Usage:
  logger = StructuredLogger(log_dir="logs/runs")
  logger.start_run(run_record)
  logger.log_decision(decision_record)
  logger.log_turn(turn_log)
  logger.log_event(global_event)
  logger.complete_run(run_id, outcome)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from world.events import DecisionRecord, TurnLog, GlobalEvent, RunRecord


class StructuredLogger:

    def __init__(self, log_dir: str = "logs/runs", run_id: Optional[str] = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if run_id is None:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_id = f"run_{ts}"
        self.run_id = run_id

        db_path = self.log_dir / f"{run_id}.db"
        self.conn = sqlite3.connect(str(db_path))
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id          TEXT PRIMARY KEY,
                scenario_name   TEXT,
                doctrine_condition TEXT,
                provider_name   TEXT,
                model_id        TEXT,
                run_number      INTEGER,
                seed            INTEGER,
                started_at      TEXT,
                completed_at    TEXT,
                completed       INTEGER DEFAULT 0,
                total_turns     INTEGER,
                final_crisis_phase TEXT,
                final_global_tension REAL,
                outcome_classification TEXT
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id              TEXT PRIMARY KEY,
                run_id          TEXT,
                turn            INTEGER,
                actor_short_name TEXT,
                doctrine_condition TEXT,
                provider_name   TEXT,
                model_id        TEXT,
                system_prompt   TEXT,
                perception_block TEXT,
                perception_metadata TEXT,
                reasoning_trace TEXT,
                raw_llm_response TEXT,
                parsed_action   TEXT,
                provider_usage  TEXT,
                usage_prompt_tokens INTEGER,
                usage_completion_tokens INTEGER,
                usage_total_tokens INTEGER,
                provider_latency_ms REAL,
                compatibility_strategy TEXT,
                finish_reason   TEXT,
                validation_result TEXT,
                validation_errors TEXT,
                retry_count     INTEGER,
                final_applied   INTEGER,
                crisis_phase_at_decision TEXT,
                doctrine_language_score REAL,
                doctrine_logic_score REAL,
                doctrine_consistent_decision INTEGER,
                contamination_flag INTEGER,
                timestamp       TEXT
            );

            CREATE TABLE IF NOT EXISTS turn_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT,
                turn            INTEGER,
                doctrine_condition TEXT,
                crisis_phase    TEXT,
                global_tension  REAL,
                pressure_before TEXT,
                pressure_after  TEXT,
                terminal_condition_met TEXT,
                event_generation_audit TEXT,
                perception_packets TEXT,
                state_mutations TEXT,
                terminal_checks TEXT,
                world_state_snapshot TEXT,
                timestamp       TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id              TEXT PRIMARY KEY,
                run_id          TEXT,
                turn            INTEGER,
                category        TEXT,
                description     TEXT,
                source          TEXT,
                caused_by_actor TEXT,
                affected_actors TEXT,
                event_family    TEXT,
                eligibility_reasons TEXT,
                provenance      TEXT,
                world_state_delta TEXT,
                timestamp       TEXT
            );
        """)
        self._ensure_columns("runs", {
            "seed": "INTEGER",
            "provider_name": "TEXT",
            "model_id": "TEXT",
        })
        self._ensure_columns("decisions", {
            "perception_metadata": "TEXT",
            "provider_name": "TEXT",
            "model_id": "TEXT",
            "provider_usage": "TEXT",
            "usage_prompt_tokens": "INTEGER",
            "usage_completion_tokens": "INTEGER",
            "usage_total_tokens": "INTEGER",
            "provider_latency_ms": "REAL",
            "compatibility_strategy": "TEXT",
            "finish_reason": "TEXT",
        })
        self._ensure_columns("turn_logs", {
            "pressure_before": "TEXT",
            "pressure_after": "TEXT",
            "event_generation_audit": "TEXT",
            "perception_packets": "TEXT",
            "state_mutations": "TEXT",
            "terminal_checks": "TEXT",
        })
        self._ensure_columns("events", {
            "event_family": "TEXT",
            "eligibility_reasons": "TEXT",
            "provenance": "TEXT",
        })
        self.conn.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for name, col_type in columns.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

    # ── Public API ────────────────────────────────────────────────────────────

    def start_run(self, record: RunRecord) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO runs
            (run_id, scenario_name, doctrine_condition, provider_name, model_id, run_number, seed,
             started_at, completed, total_turns, final_crisis_phase,
             final_global_tension, outcome_classification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '', 0.0, NULL)
        """, (
            record.run_id, record.scenario_name, record.doctrine_condition,
            record.provider_name, record.model_id, record.run_number,
            record.seed, record.started_at.isoformat(),
        ))
        self.conn.commit()

    def log_decision(self, record: DecisionRecord) -> None:
        provider_usage = record.provider_usage or {}
        prompt_tokens = (
            provider_usage.get("prompt_tokens")
            or provider_usage.get("input_tokens")
            or 0
        )
        completion_tokens = (
            provider_usage.get("completion_tokens")
            or provider_usage.get("output_tokens")
            or 0
        )
        total_tokens = provider_usage.get("total_tokens")
        if total_tokens is None:
            total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)

        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO decisions
            (id, run_id, turn, actor_short_name, doctrine_condition, provider_name, model_id,
             system_prompt, perception_block, perception_metadata,
             reasoning_trace, raw_llm_response, parsed_action, provider_usage,
             usage_prompt_tokens, usage_completion_tokens, usage_total_tokens,
             provider_latency_ms, compatibility_strategy, finish_reason,
             validation_result, validation_errors, retry_count,
             final_applied, crisis_phase_at_decision,
             doctrine_language_score, doctrine_logic_score,
             doctrine_consistent_decision, contamination_flag, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.id, record.run_id, record.turn, record.actor_short_name,
            record.doctrine_condition, record.provider_name, record.model_id,
            record.system_prompt, record.perception_block,
            json.dumps(record.perception_metadata),
            record.reasoning_trace, record.raw_llm_response,
            json.dumps(record.parsed_action) if record.parsed_action else None,
            json.dumps(provider_usage),
            prompt_tokens,
            completion_tokens,
            total_tokens,
            provider_usage.get("decision_latency_ms") or provider_usage.get("provider_latency_ms"),
            provider_usage.get("compatibility_strategy"),
            provider_usage.get("finish_reason"),
            record.validation_result,
            json.dumps(record.validation_errors),
            record.retry_count, int(record.final_applied),
            record.crisis_phase_at_decision,
            record.doctrine_language_score, record.doctrine_logic_score,
            int(record.doctrine_consistent_decision) if record.doctrine_consistent_decision is not None else None,
            int(record.contamination_flag) if record.contamination_flag is not None else None,
            record.timestamp.isoformat(),
        ))
        self.conn.commit()

    def log_turn(self, turn_log: TurnLog) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO turn_logs
            (run_id, turn, doctrine_condition, crisis_phase, global_tension,
             pressure_before, pressure_after, terminal_condition_met,
             event_generation_audit, perception_packets, state_mutations,
             terminal_checks, world_state_snapshot, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            turn_log.run_id, turn_log.turn, turn_log.doctrine_condition,
            turn_log.crisis_phase, turn_log.global_tension,
            json.dumps(turn_log.pressure_before),
            json.dumps(turn_log.pressure_after),
            turn_log.terminal_condition_met,
            json.dumps(turn_log.event_generation_audit),
            json.dumps(turn_log.perception_packets),
            json.dumps(turn_log.state_mutations),
            json.dumps(turn_log.terminal_checks),
            json.dumps(turn_log.world_state_snapshot),
            turn_log.timestamp.isoformat(),
        ))
        self.conn.commit()

    def log_event(self, event: GlobalEvent, run_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO events
            (id, run_id, turn, category, description, source, caused_by_actor,
             affected_actors, event_family, eligibility_reasons, provenance,
             world_state_delta, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.id, run_id, event.turn, event.category, event.description,
            event.source, event.caused_by_actor,
            json.dumps(event.affected_actors),
            event.event_family,
            json.dumps(event.eligibility_reasons),
            json.dumps(event.provenance),
            json.dumps(event.world_state_delta),
            event.timestamp.isoformat(),
        ))
        self.conn.commit()

    def complete_run(
        self,
        run_id: str,
        total_turns: int,
        final_crisis_phase: str,
        final_global_tension: float,
        outcome_classification: Optional[str],
    ) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE runs SET
                completed = 1,
                completed_at = ?,
                total_turns = ?,
                final_crisis_phase = ?,
                final_global_tension = ?,
                outcome_classification = ?
            WHERE run_id = ?
        """, (
            datetime.utcnow().isoformat(),
            total_turns, final_crisis_phase,
            final_global_tension, outcome_classification,
            run_id,
        ))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
