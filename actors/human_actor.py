"""
HumanDecisionActor — CLI-driven actor for human-in-loop wargame play.

Same engine seam as LLMDecisionActor: subclass ActorInterface, return
(BaseAction, DecisionRecord) from decide(). The engine treats it
polymorphically; PRC/TWN/JPN still run on the LLM path.

Inputs reused from the LLM path:
  - engine.perception.build_perception_packet — same fog-of-war filter
  - engine.actions.get_available_actions_for  — pre-filtered valid menu
  - engine.actions.parse_action_from_dict     — same parser
  - engine.validator.ActionValidator          — safety-net re-check
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from world.state import Actor, WorldState
from world.events import DecisionRecord
from engine.actions import (
    BaseAction,
    ACTION_REGISTRY,
    parse_action_from_dict,
    get_available_actions_for,
)
from engine.validator import ActionValidator
from engine.perception import build_perception_packet
from actors.base import ActorInterface


_INTENSITIES = ["low", "medium", "high"]


def _short_doc(action_type: str) -> str:
    """One-line description of an action class. Pulled from the class docstring
    when present, otherwise a labeled fallback."""
    cls = ACTION_REGISTRY[action_type]
    doc = (cls.__doc__ or "").strip()
    if doc:
        return doc.splitlines()[0].strip()
    return f"({action_type})"


def _format_self_view(perc_self: Dict[str, Any]) -> List[str]:
    return [
        f"  Posture:   {perc_self.get('posture', '?')}",
        f"  Forces:    conv={perc_self.get('conventional_forces')} | naval={perc_self.get('naval_power')} | air={perc_self.get('air_superiority')} | nuc={perc_self.get('nuclear_capability')}",
        f"  Readiness: {perc_self.get('readiness')}  | amphibious={perc_self.get('amphibious_capacity')} | A2/AD={perc_self.get('a2ad_effectiveness')}",
        f"  Economy:   GDP={perc_self.get('gdp_strength')} | reserves={perc_self.get('foreign_reserves')} | energy_indep={perc_self.get('energy_independence')} | industrial={perc_self.get('industrial_capacity')}",
        f"  Politics:  stability={perc_self.get('domestic_stability')} | legitimacy={perc_self.get('regime_legitimacy')} | unity={perc_self.get('decision_unity')} | casualty_tolerance={perc_self.get('casualty_tolerance')}",
    ]


def _format_other_view(name: str, other: Dict[str, Any]) -> List[str]:
    return [
        f"  {name}: posture={other.get('posture')}  confidence={other.get('assessment_confidence')}",
        f"      forces conv={other.get('conventional_forces')} naval={other.get('naval_power')} air={other.get('air_superiority')} readiness={other.get('readiness')}",
        f"      economy GDP={other.get('gdp_strength')} reserves={other.get('foreign_reserves')} industrial={other.get('industrial_capacity')}",
    ]


class HumanDecisionActor(ActorInterface):
    """
    Human-controlled actor. On each decide() call:
      1. Build the same fog-of-war perception packet the LLM would receive.
      2. Print a turn briefing: self view + perception of others.
      3. Show a numbered menu of valid action types for this turn.
      4. Prompt for target / intensity / rationale.
      5. Build and validate the action. Reprompt on validation failure.
      6. Return (action, DecisionRecord) with provider_name='human'.
    """

    def __init__(
        self,
        actor: Actor,
        run_id: str,
        doctrine_condition: str = "human",
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
    ):
        self.actor = actor
        self.run_id = run_id
        self.doctrine_condition = doctrine_condition
        self._validator = ActionValidator()
        self._input = input_fn
        self._print = print_fn

    # ── Public API ───────────────────────────────────────────────────────────

    def decide(self, state: WorldState) -> Tuple[BaseAction, DecisionRecord]:
        state.ensure_derived_state()
        self.actor = state.actors[self.actor.short_name]

        perception, perception_metadata = build_perception_packet(self.actor, state)
        recent_events = self._extract_recent_events(state)
        available = sorted(get_available_actions_for(self.actor.short_name, state))

        self._render_briefing(state, perception, recent_events, available)

        started = time.perf_counter()
        action, rationale, retries = self._prompt_until_valid(state, available)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        record = DecisionRecord(
            turn=state.turn,
            actor_short_name=self.actor.short_name,
            doctrine_condition=self.doctrine_condition,
            run_id=self.run_id,
            provider_name="human",
            model_id="human",
            system_prompt=f"[human player] actor={self.actor.short_name}",
            perception_block=json.dumps(perception, indent=2),
            perception_metadata=perception_metadata,
            reasoning_trace=rationale or "[no rationale]",
            raw_llm_response="",
            parsed_action=action.model_dump(),
            provider_usage={
                "decision_latency_ms": elapsed_ms,
                "attempt_count": retries + 1,
                "input_source": "human_cli",
            },
            validation_result="valid",
            validation_errors=[],
            retry_count=retries,
            final_applied=True,
            crisis_phase_at_decision=state.crisis_phase,
        )
        return action, record

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render_briefing(
        self,
        state: WorldState,
        perception: Dict[str, Any],
        recent_events: List[str],
        available: List[str],
    ) -> None:
        bar = "=" * 72
        self._print("")
        self._print(bar)
        self._print(f" TURN {state.turn}  |  {self.actor.short_name} ({self.actor.name})  |  phase={state.crisis_phase}  tension={state.global_tension:.2f}")
        self._print(bar)

        self._print("YOUR SITUATION")
        for line in _format_self_view(perception["self"]):
            self._print(line)

        others = perception.get("others", {})
        if others:
            self._print("")
            self._print("PERCEIVED ADVERSARIES / OBSERVERS  (qualitative bands; fog-of-war)")
            for other_name, packet in others.items():
                for line in _format_other_view(other_name, packet):
                    self._print(line)

        rels = perception.get("relationships", [])
        if rels:
            self._print("")
            self._print("BILATERAL RELATIONSHIPS")
            for r in rels:
                self._print(
                    f"  vs {r['with']}: {r['type']}  trust={r['trust']}  alliance={r['alliance_strength']}  threat={r['threat_perception']}  deterrence={r['deterrence_credibility']}"
                )

        systemic = perception.get("systemic", {})
        if systemic:
            self._print("")
            self._print("SYSTEMIC SIGNALS")
            for k, v in systemic.items():
                self._print(f"  {k}: {v}")

        uncertainty = perception.get("uncertainty", {})
        if uncertainty:
            self._print("")
            self._print(f"UNCERTAINTY: {uncertainty.get('level', '?')}")
            for sig in uncertainty.get("contradictory_signals", []):
                self._print(f"  ! {sig}")

        if recent_events:
            self._print("")
            self._print("RECENT EVENTS")
            for e in recent_events[:10]:
                self._print(f"  - {e}")

        self._print("")
        self._print(f"AVAILABLE ACTIONS  ({len(available)})")
        for i, a in enumerate(available, 1):
            self._print(f"  [{i:>2}] {a:<28} {_short_doc(a)}")
        self._print("")

    # ── Prompting ────────────────────────────────────────────────────────────

    def _prompt_until_valid(
        self,
        state: WorldState,
        available: List[str],
    ) -> Tuple[BaseAction, str, int]:
        other_actors = [n for n in state.actors.keys() if n != self.actor.short_name]
        attempts = 0
        while True:
            action_type = self._prompt_action(available)
            target_actor = self._prompt_target_actor(action_type, other_actors)
            intensity = self._prompt_intensity()
            rationale = self._prompt_rationale()

            payload: Dict[str, Any] = {
                "action_type": action_type,
                "actor_id": self.actor.short_name,
                "intensity": intensity,
                "rationale": rationale or "[human input]",
            }
            if target_actor:
                payload["target_actor"] = target_actor

            try:
                candidate = parse_action_from_dict(payload)
            except Exception as exc:
                self._print(f"! Could not build action: {exc}. Try again.")
                attempts += 1
                continue

            result = self._validator.validate(candidate, state)
            if result.is_valid:
                return candidate, rationale, attempts

            self._print("! Action rejected by validator:")
            for err in result.errors:
                self._print(f"    - {err}")
            self._print("  Pick again.\n")
            attempts += 1

    def _prompt_action(self, available: List[str]) -> str:
        while True:
            raw = self._input("> Pick action # (or type name): ").strip()
            if not raw:
                self._print("  Enter a number or an action name.")
                continue
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(available):
                    return available[idx - 1]
                self._print(f"  Out of range (1..{len(available)}).")
                continue
            if raw in available:
                return raw
            if raw in ACTION_REGISTRY and raw not in available:
                self._print(f"  '{raw}' is in the registry but not valid for you this turn.")
                continue
            self._print(f"  Unknown action '{raw}'. Pick from the menu above.")

    def _prompt_target_actor(self, action_type: str, other_actors: List[str]) -> Optional[str]:
        if action_type in ("hold_position", "monitor"):
            return None
        if not other_actors:
            return None
        listing = "  ".join(f"{i+1}={name}" for i, name in enumerate(other_actors))
        while True:
            raw = self._input(f"> Target actor ({listing}, or blank for none): ").strip()
            if not raw:
                return None
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(other_actors):
                    return other_actors[idx - 1]
                self._print(f"  Out of range (1..{len(other_actors)}).")
                continue
            if raw in other_actors:
                return raw
            self._print(f"  Unknown actor '{raw}'.")

    def _prompt_intensity(self) -> str:
        raw = self._input("> Intensity [low/medium/high] (blank=medium): ").strip().lower()
        if not raw:
            return "medium"
        if raw in _INTENSITIES:
            return raw
        self._print(f"  Unknown intensity '{raw}', defaulting to medium.")
        return "medium"

    def _prompt_rationale(self) -> str:
        return self._input("> Rationale (optional, press enter to skip): ").strip()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_recent_events(self, state: WorldState) -> List[str]:
        if not state.turn_logs:
            return []
        last_log = state.turn_logs[-1]
        events: List[str] = []
        if hasattr(last_log, "events_this_turn"):
            events += [e.description for e in last_log.events_this_turn]
        if hasattr(last_log, "cascade_events"):
            events += [f"[CASCADE] {e.description}" for e in last_log.cascade_events]
        return events
