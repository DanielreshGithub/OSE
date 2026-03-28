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
import os
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
                run_number      INTEGER,
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
                system_prompt   TEXT,
                perception_block TEXT,
                reasoning_trace TEXT,
                raw_llm_response TEXT,
                parsed_action   TEXT,
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
                terminal_condition_met TEXT,
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
                world_state_delta TEXT,
                timestamp       TEXT
            );
        """)
        self.conn.commit()

    # ── Public API ────────────────────────────────────────────────────────────

    def start_run(self, record: RunRecord) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO runs
            (run_id, scenario_name, doctrine_condition, run_number,
             started_at, completed, total_turns, final_crisis_phase,
             final_global_tension, outcome_classification)
            VALUES (?, ?, ?, ?, ?, 0, 0, '', 0.0, NULL)
        """, (
            record.run_id, record.scenario_name, record.doctrine_condition,
            record.run_number, record.started_at.isoformat(),
        ))
        self.conn.commit()

    def log_decision(self, record: DecisionRecord) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO decisions
            (id, run_id, turn, actor_short_name, doctrine_condition,
             system_prompt, perception_block, reasoning_trace, raw_llm_response,
             parsed_action, validation_result, validation_errors, retry_count,
             final_applied, crisis_phase_at_decision,
             doctrine_language_score, doctrine_logic_score,
             doctrine_consistent_decision, contamination_flag, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.id, record.run_id, record.turn, record.actor_short_name,
            record.doctrine_condition, record.system_prompt, record.perception_block,
            record.reasoning_trace, record.raw_llm_response,
            json.dumps(record.parsed_action) if record.parsed_action else None,
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
             terminal_condition_met, world_state_snapshot, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            turn_log.run_id, turn_log.turn, turn_log.doctrine_condition,
            turn_log.crisis_phase, turn_log.global_tension,
            turn_log.terminal_condition_met,
            json.dumps(turn_log.world_state_snapshot),
            turn_log.timestamp.isoformat(),
        ))
        self.conn.commit()

    def log_event(self, event: GlobalEvent, run_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO events
            (id, run_id, turn, category, description, source, caused_by_actor,
             affected_actors, world_state_delta, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.id, run_id, event.turn, event.category, event.description,
            event.source, event.caused_by_actor,
            json.dumps(event.affected_actors),
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
