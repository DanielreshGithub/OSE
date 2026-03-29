"""
SimulationEngine — full turn lifecycle orchestrator for OSE.

Turn lifecycle:
  1. Inject scenario events (turn-specific triggers)
  2. Collect decisions from all active actors (simultaneous, no turn-order bias)
  3. Resolve simultaneous actions (TurnResolver — conflict adjudication)
  4. Detect and apply cascade effects (CascadeDetector)
  5. Log the turn (StructuredLogger — SQLite)
  6. Display turn summary (Rich terminal output)
  7. Check terminal conditions

Terminal conditions:
  - crisis_phase == "war" AND global_tension >= 0.90  →  "deterrence_failure"
  - crisis_phase in ("peacetime", "tension") AND global_tension <= 0.35  →  "deterrence_success"
  - All actors in defensive posture for 3+ consecutive turns  →  "frozen_conflict"
  - max_turns reached  →  outcome classified by final state
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from world.state import WorldState, Actor
from world.pressures import PressureState
from world.events import GlobalEvent, TurnLog, RunRecord, DecisionRecord
from engine.actions import BaseAction
from engine.pressures import ScenarioPressureModel
from engine.resolver import TurnResolver
from engine.cascade import CascadeDetector
from logs.logger import StructuredLogger

console = Console()

# Tension display colors
def _tension_color(t: float) -> str:
    if t >= 0.75:
        return "bold red"
    elif t >= 0.50:
        return "bold yellow"
    elif t >= 0.30:
        return "yellow"
    return "green"

def _phase_color(phase: str) -> str:
    colors = {
        "peacetime": "green", "tension": "yellow",
        "crisis": "bold yellow", "war": "bold red",
        "post_conflict": "blue",
    }
    return colors.get(phase, "white")


class SimulationEngine:
    """
    Orchestrates the full simulation lifecycle.
    Instantiated once per run; not reused across runs.
    """

    def __init__(
        self,
        state: WorldState,
        actors: Dict[str, Any],          # short_name -> LLMDecisionActor
        doctrine_condition: str,
        run_id: Optional[str] = None,
        run_number: int = 1,
        seed: int = 0,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
        log_dir: str = "logs/runs",
        verbose: bool = True,
        scenario: Optional[Any] = None,  # ScenarioDefinition — for dynamic per-turn events
    ):
        self.state = state
        self.actors = actors
        self.doctrine_condition = doctrine_condition
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.run_number = run_number
        self.seed = int(seed)
        self.provider_name = provider_name or "unknown"
        self.model_id = model_id or "unknown"
        self.verbose = verbose
        self._scenario = scenario        # If provided, call get_turn_events(turn, state) live

        self.state.random_seed = self.seed
        self.state.ensure_derived_state()
        if self._scenario is not None:
            setattr(self._scenario, "seed", self.seed)

        self._resolver = TurnResolver()
        self._cascade = CascadeDetector()
        self._pressure_model = ScenarioPressureModel(self.state.scenario_id)
        self._logger = StructuredLogger(log_dir=log_dir, run_id=self.run_id)

        # Terminal condition tracking
        self._consecutive_defensive_turns: Dict[str, int] = {
            name: 0 for name in actors
        }
        self._outcome: Optional[str] = None

    def run(
        self,
        max_turns: int,
        scenario_events: Optional[Dict[int, List[GlobalEvent]]] = None,
    ) -> Tuple[WorldState, str]:
        """
        Run the simulation for up to max_turns turns.

        If self._scenario is set, get_turn_events() is called dynamically each
        turn against the current world state (supports stochastic event pools).
        Otherwise falls back to the static scenario_events dict.
        Returns (final_state, outcome_classification)
        """
        scenario_events = scenario_events or {}

        run_record = RunRecord(
            run_id=self.run_id,
            scenario_name=self.state.scenario_name,
            doctrine_condition=self.doctrine_condition,
            provider_name=self.provider_name,
            model_id=self.model_id,
            run_number=self.run_number,
            seed=self.seed,
            total_turns=max_turns,
            final_crisis_phase=self.state.crisis_phase,
            final_global_tension=self.state.global_tension,
        )
        self._logger.start_run(run_record)

        if self.verbose:
            self._display_header()

        for turn in range(max_turns):
            self.state.turn = turn

            # 1. Inject scenario events (dynamic if scenario provided, static otherwise)
            if self._scenario is not None:
                injected = self._scenario.get_turn_events(turn, self.state)
            else:
                injected = scenario_events.get(turn, [])
            pressure_before, event_generation_audit, visible_injected = self._extract_scenario_audit(injected)
            self.state.pressures = pressure_before
            self._apply_injected_events(injected)
            self.state.ensure_derived_state()

            if self.verbose:
                self._display_turn_header(turn)

            # 2. Collect decisions (all actors simultaneously)
            decisions: Dict[str, Tuple[BaseAction, DecisionRecord]] = {}
            for name, actor_agent in self.actors.items():
                actor = self.state.get_actor(name)
                if actor is None or not actor.is_active:
                    continue
                if self.verbose:
                    console.print(f"  [dim]⟳ {name} deciding...[/dim]")
                action, record = actor_agent.decide(self.state)
                decisions[name] = (action, record)

            # 3. Resolve simultaneous actions
            self.state, turn_events = self._resolver.resolve(decisions, self.state)

            # 4. Cascade detection
            self.state, cascade_events = self._cascade.detect(self.state, decisions)
            all_events = injected + turn_events + cascade_events
            pressure_after = self._pressure_model.compute(
                self.state,
                turn_actions=decisions,
                recent_events=all_events,
                previous=pressure_before,
            )
            self.state.pressures = pressure_after
            self.state.ensure_derived_state()

            terminal, terminal_checks = self._evaluate_terminal(decisions)

            # 5. Log all events
            for event in all_events:
                self._logger.log_event(event, self.run_id)

            # Log decisions
            for name, (action, record) in decisions.items():
                self._logger.log_decision(record)
                # Add to world state history
                self.state.decision_history.append(record)

            # Build and log turn log
            turn_log = TurnLog(
                run_id=self.run_id,
                turn=turn,
                doctrine_condition=self.doctrine_condition,
                crisis_phase=self.state.crisis_phase,
                global_tension=self.state.global_tension,
                pressure_before=pressure_before.to_trace(),
                pressure_after=pressure_after.to_trace(),
                events_this_turn=visible_injected + turn_events,
                decisions=[record for _, record in decisions.values()],
                cascade_events=cascade_events,
                event_generation_audit=event_generation_audit,
                perception_packets=self._collect_perception_packets(decisions),
                state_mutations=self._collect_state_mutations(decisions, all_events),
                terminal_checks=terminal_checks,
                world_state_snapshot=self._snapshot(),
                terminal_condition_met=terminal,
            )
            self.state.turn_logs.append(turn_log)
            self._logger.log_turn(turn_log)

            # 6. Display
            if self.verbose:
                self._display_turn_summary(turn, decisions, visible_injected + turn_events, cascade_events)

            # 7. Check terminal conditions
            if terminal:
                self._outcome = terminal
                if self.verbose:
                    console.print(
                        Panel(
                            f"[bold]Terminal condition:[/bold] {terminal}",
                            style="bold red" if "failure" in terminal else "bold green",
                        )
                    )
                break

        outcome = self._outcome or self._classify_final_outcome()
        self._logger.complete_run(
            self.run_id,
            total_turns=self.state.turn + 1,
            final_crisis_phase=self.state.crisis_phase,
            final_global_tension=self.state.global_tension,
            outcome_classification=outcome,
        )
        self._logger.close()

        if self.verbose:
            self._display_footer(outcome)

        return self.state, outcome

    # ── Event application ─────────────────────────────────────────────────────

    def _apply_injected_events(self, events: List[GlobalEvent]) -> None:
        """Apply pre-scripted scenario events to world state."""
        for event in events:
            # Injected events are narrative — they affect tension but not resources directly
            # Specific scenarios customize this via subclassing or delta dicts
            delta = event.world_state_delta
            if "global_tension_delta" in delta:
                self.state.global_tension = max(0.0, min(1.0,
                self.state.global_tension + float(delta["global_tension_delta"])
                ))

    def _extract_scenario_audit(
        self,
        events: List[GlobalEvent],
    ) -> Tuple[PressureState, List[Dict[str, Any]], List[GlobalEvent]]:
        pressure_state = self._pressure_model.compute(self.state, previous=self.state.pressures)
        audit: List[Dict[str, Any]] = []
        visible_events: List[GlobalEvent] = []
        for event in events:
            delta = event.world_state_delta or {}
            pressure_snapshot = delta.get("pressure_snapshot")
            if pressure_snapshot:
                pressure_state = self._pressure_state_from_snapshot(pressure_snapshot)
                audit_payload = delta.get("audit")
                if isinstance(audit_payload, dict):
                    audit = [audit_payload]
                elif isinstance(audit_payload, list):
                    audit = audit_payload
                continue
            visible_events.append(event)
        return pressure_state, audit, visible_events

    def _pressure_state_from_snapshot(self, snapshot: Dict[str, Any]) -> PressureState:
        return PressureState(
            military_pressure=float(snapshot.get("military_pressure", 0.0)),
            diplomatic_pressure=float(snapshot.get("diplomatic_pressure", 0.0)),
            alliance_pressure=float(snapshot.get("alliance_pressure", 0.0)),
            domestic_pressure=float(snapshot.get("domestic_pressure", 0.0)),
            economic_pressure=float(snapshot.get("economic_pressure", 0.0)),
            informational_pressure=float(
                snapshot.get("informational_pressure", snapshot.get("information_pressure", 0.0))
            ),
            crisis_instability=float(snapshot.get("crisis_instability", 0.0)),
            uncertainty=float(snapshot.get("uncertainty", 0.0)),
            turn=int(snapshot.get("turn", self.state.turn)),
            scenario_id=str(snapshot.get("notes", {}).get("scenario_id", self.state.scenario_id)),
            metadata={
                "source": "scenario_audit",
                "snapshot": snapshot,
            },
        )

    def _collect_perception_packets(
        self,
        decisions: Dict[str, Tuple[BaseAction, DecisionRecord]],
    ) -> Dict[str, Any]:
        packets: Dict[str, Any] = {}
        for actor_id, (_, record) in decisions.items():
            try:
                packets[actor_id] = {
                    "packet": json.loads(record.perception_block),
                    "metadata": record.perception_metadata,
                }
            except json.JSONDecodeError:
                packets[actor_id] = {
                    "packet": record.perception_block,
                    "metadata": record.perception_metadata,
                }
        return packets

    def _collect_state_mutations(
        self,
        decisions: Dict[str, Tuple[BaseAction, DecisionRecord]],
        events: List[GlobalEvent],
    ) -> List[Dict[str, Any]]:
        mutations: List[Dict[str, Any]] = []
        for actor_id, (action, _) in decisions.items():
            mutations.append({
                "actor": actor_id,
                "action_type": action.action_type,
                "expected_effects": action.get_expected_effects(),
            })
        for event in events:
            if event.world_state_delta:
                mutations.append({
                    "event": event.description,
                    "source": event.source,
                    "delta": event.world_state_delta,
                })
        return mutations

    # ── Terminal condition checks ─────────────────────────────────────────────

    def _evaluate_terminal(
        self, decisions: Dict[str, Tuple[BaseAction, Any]]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        from engine.actions import DefensivePostureAction, HoldPositionAction, MonitorAction

        details = {
            "war_failure": self.state.crisis_phase == "war" and self.state.global_tension >= 0.90,
            # Minimum 3 turns before de-escalation can terminate — prevents spurious
            # early-exit when all actors cooperate on turn 0-1.
            "deescalation_success": (
                self.state.turn >= 3
                and self.state.crisis_phase in ("peacetime", "tension")
                and self.state.global_tension <= 0.30
            ),
            "all_passive_for_three_turns": False,
            "per_actor_passive_streaks": {},
        }

        # Deterrence failure: war phase + high tension
        if details["war_failure"]:
            return "deterrence_failure", details

        # Deterrence success: de-escalated to low tension
        if details["deescalation_success"]:
            return "deterrence_success", details

        # Frozen conflict: all actors in passive posture for 3+ turns
        for name, (action, _) in decisions.items():
            if isinstance(action, (DefensivePostureAction, HoldPositionAction, MonitorAction)):
                self._consecutive_defensive_turns[name] = \
                    self._consecutive_defensive_turns.get(name, 0) + 1
            else:
                self._consecutive_defensive_turns[name] = 0
        details["per_actor_passive_streaks"] = dict(self._consecutive_defensive_turns)

        if all(v >= 3 for v in self._consecutive_defensive_turns.values()):
            details["all_passive_for_three_turns"] = True
            return "frozen_conflict", details

        return None, details

    def _classify_final_outcome(self) -> str:
        """Classify outcome when max_turns is reached without terminal condition."""
        if self.state.crisis_phase == "war":
            return "deterrence_failure"
        elif self.state.global_tension <= 0.40:
            return "deterrence_success"
        elif self.state.crisis_phase in ("crisis", "tension"):
            return "frozen_conflict"
        else:
            return "defense_success"

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def _snapshot(self) -> Dict[str, Any]:
        """Serialize key world state metrics for the turn log."""
        snap: Dict[str, Any] = {
            "turn": self.state.turn,
            "crisis_phase": self.state.crisis_phase,
            "global_tension": round(self.state.global_tension, 3),
            "pressures": self.state.pressures.to_trace(),
            "actors": {},
        }
        for name, actor in self.state.actors.items():
            snap["actors"][name] = {
                "military_readiness": round(actor.military.readiness, 3),
                "conventional_forces": round(actor.military.conventional_forces, 3),
                "gdp_strength": round(actor.economic.gdp_strength, 3),
                "domestic_stability": round(actor.political.domestic_stability, 3),
                "posture": actor.current_posture,
            }
        snap["systemic"] = {
            "semiconductor_supply_chain": round(
                self.state.systemic.semiconductor_supply_chain_integrity, 3
            ),
            "global_shipping_disruption": round(
                self.state.systemic.global_shipping_disruption, 3
            ),
            "alliance_cohesion": round(
                self.state.systemic.alliance_system_cohesion, 3
            ),
        }
        return snap

    # ── Rich display ──────────────────────────────────────────────────────────

    def _display_header(self) -> None:
        console.rule(
            f"[bold blue]OSE — {self.state.scenario_name}[/bold blue]  "
            f"[dim]doctrine: {self.doctrine_condition} | run: {self.run_id} | seed: {self.seed}[/dim]"
        )

    def _display_turn_header(self, turn: int) -> None:
        tension = self.state.global_tension
        phase = self.state.crisis_phase
        console.print()
        console.rule(
            f"[bold]Turn {turn}[/bold]  "
            f"[{_phase_color(phase)}]Phase: {phase.upper()}[/{_phase_color(phase)}]  "
            f"[{_tension_color(tension)}]Tension: {tension:.2f}[/{_tension_color(tension)}]"
        )

    def _display_turn_summary(
        self,
        turn: int,
        decisions: Dict[str, Tuple[BaseAction, DecisionRecord]],
        turn_events: List[GlobalEvent],
        cascade_events: List[GlobalEvent],
    ) -> None:
        # Actor decisions table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Actor", width=6)
        table.add_column("Action", width=20)
        table.add_column("Target", width=8)
        table.add_column("Intensity", width=9)
        table.add_column("Valid", width=5)
        table.add_column("Reasoning (excerpt)", width=60)

        for name, (action, record) in decisions.items():
            reasoning_excerpt = record.reasoning_trace[:80].replace("\n", " ") + "…" \
                if len(record.reasoning_trace) > 80 else record.reasoning_trace.replace("\n", " ")
            valid_str = "[green]✓[/green]" if record.final_applied else "[red]✗[/red]"
            table.add_row(
                name,
                action.action_type,
                action.target_actor or action.target_zone or "—",
                action.intensity,
                valid_str,
                reasoning_excerpt,
            )
        console.print(table)

        # Events
        if turn_events or cascade_events:
            for e in turn_events:
                console.print(f"  [dim]↳ {e.description}[/dim]")
            for e in cascade_events:
                console.print(f"  [bold yellow]↳ {e.description}[/bold yellow]")

        # World state summary row
        tension = self.state.global_tension
        console.print(
            f"  [dim]State:[/dim] "
            f"[{_tension_color(tension)}]tension={tension:.2f}[/{_tension_color(tension)}]  "
            + "  ".join(
                f"{n}: forces={a.military.conventional_forces:.2f} "
                f"rdns={a.military.readiness:.2f} "
                f"gdp={a.economic.gdp_strength:.2f}"
                for n, a in self.state.actors.items()
            )
        )

    def _display_footer(self, outcome: str) -> None:
        console.print()
        console.rule("[bold]Simulation Complete[/bold]")
        style = "bold green" if outcome in ("deterrence_success", "defense_success") else "bold red"
        console.print(Panel(
            f"[bold]Outcome:[/bold] {outcome}\n"
            f"[bold]Final phase:[/bold] {self.state.crisis_phase}\n"
            f"[bold]Final tension:[/bold] {self.state.global_tension:.2f}\n"
            f"[bold]Log:[/bold] logs/runs/{self.run_id}.db",
            title="Run Complete",
            style=style,
        ))
