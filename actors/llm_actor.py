"""
LLMDecisionActor — the core OSE actor implementation.

Pipeline per turn:
  1. build_perception()     — filter + noise world state for this actor
  2. build_persona_prompt() — stable system prompt (persona + doctrine)
  3. build_decision_prompt()— per-turn user prompt with situation + schema
  4. provider.call()        — LLM call via tool/function use (any provider)
  5. parse + validate       — ActionValidator; retry up to MAX_RETRIES on failure
  6. Return (action, DecisionRecord)

The LLM never touches world state directly.
The validator is the firewall — pure rule-based, no LLM.
Provider is injected — swap Anthropic for OpenRouter at construction time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from world.state import Actor, WorldState
from world.events import DecisionRecord
from engine.actions import (
    BaseAction, ACTION_REGISTRY, parse_action_from_dict,
    get_available_actions_for,
)
from engine.validator import ActionValidator
from engine.perception import build_perception_packet
from actors.base import ActorInterface
from actors.persona import build_persona_prompt
from providers.base import LLMProvider

MAX_RETRIES = 2

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── Qualitative band conversion ───────────────────────────────────────────────

def _to_band(value: float) -> str:
    """Convert normalized float to qualitative band."""
    if value >= 0.65:
        return "HIGH"
    elif value >= 0.35:
        return "MEDIUM"
    else:
        return "LOW"


# ── Decision Prompt Builder ───────────────────────────────────────────────────

def _format_military_summary(perc: Dict[str, str]) -> str:
    return (
        f"Conventional forces: {perc['conventional_forces']} | "
        f"Naval: {perc['naval_power']} | "
        f"Air: {perc['air_superiority']} | "
        f"Nuclear: {perc['nuclear_capability']} | "
        f"Readiness: {perc['readiness']} | "
        f"Amphibious: {perc['amphibious_capacity']} | "
        f"A2/AD: {perc['a2ad_effectiveness']}"
    )


def _format_economic_summary(perc: Dict[str, str]) -> str:
    return (
        f"GDP strength: {perc['gdp_strength']} | "
        f"Reserves: {perc['foreign_reserves']} | "
        f"Energy independence: {perc['energy_independence']} | "
        f"Trade openness: {perc['trade_openness']} | "
        f"Industrial capacity: {perc['industrial_capacity']}"
    )


def _format_political_summary(perc: Dict[str, str]) -> str:
    return (
        f"Domestic stability: {perc['domestic_stability']} | "
        f"Regime legitimacy: {perc['regime_legitimacy']} | "
        f"International standing: {perc['international_standing']} | "
        f"Decision unity: {perc['decision_unity']} | "
        f"Casualty tolerance: {perc['casualty_tolerance']} | "
        f"Current posture: {perc['posture']}"
    )


def _format_relationships(perception: Dict[str, Any]) -> str:
    rels = perception.get("relationships", [])
    if not rels:
        return "No tracked bilateral relationships."
    lines = []
    for r in rels:
        lines.append(
            f"- **{r['with']}** ({r['type']}): "
            f"Trust={r['trust']}, Alliance={r['alliance_strength']}, "
            f"Threat perception={r['threat_perception']}, "
            f"Deterrence credibility={r['deterrence_credibility']}"
        )
    for name, other in perception.get("others", {}).items():
        lines.append(
            f"  └ {name} military posture: {other['posture']} | "
            f"Forces: {other['conventional_forces']} | "
            f"Readiness: {other['readiness']} | "
            f"Confidence: {other.get('assessment_confidence', 'MEDIUM')}"
        )
    return "\n".join(lines)


def _format_pressure_summary(state: WorldState) -> str:
    pressures = getattr(state, "pressures", None)
    if pressures is None:
        return "No structured scenario pressures tracked."
    bands = pressures.as_bands()
    return (
        f"Military={bands['military_pressure']} | "
        f"Diplomatic={bands['diplomatic_pressure']} | "
        f"Alliance={bands['alliance_pressure']} | "
        f"Domestic={bands['domestic_pressure']} | "
        f"Economic={bands['economic_pressure']} | "
        f"Informational={bands['informational_pressure']} | "
        f"Instability={bands['crisis_instability']} | "
        f"Uncertainty={bands['uncertainty']}"
    )


def _format_capability_summary(actor: Actor) -> str:
    if actor.capabilities is None:
        return "No structured capability profile available."
    ordered = [
        "local_naval_projection",
        "local_air_projection",
        "missile_a2ad_capability",
        "cyber_capability",
        "intelligence_quality",
        "economic_coercion_capacity",
        "alliance_leverage",
        "logistics_endurance",
        "domestic_stability",
        "war_aversion",
        "escalation_tolerance",
        "bureaucratic_flexibility",
        "signaling_credibility",
    ]
    bands = actor.capabilities.as_bands()
    return " | ".join(f"{field}={bands[field]}" for field in ordered)


def _format_available_actions(actor_id: str, state: WorldState) -> str:
    available = get_available_actions_for(actor_id, state)
    return "\n".join(f"- `{a}`" for a in sorted(available))


def build_decision_prompt(
    actor: Actor,
    state: WorldState,
    perception: Dict[str, Any],
    recent_events: List[str],
    retry_feedback: Optional[str] = None,
) -> str:
    """Build the per-turn user prompt for an actor's decision."""
    template = (_PROMPTS_DIR / "decision.txt").read_text()

    self_perc = perception["self"]
    global_tension = state.global_tension
    tension_band = _to_band(global_tension)

    active = ", ".join(state.active_conflicts) if state.active_conflicts else "None"
    events_block = "\n".join(f"- {e}" for e in recent_events) if recent_events else "No notable events this turn."
    available_block = _format_available_actions(actor.short_name, state)
    relationships_block = _format_relationships(perception)
    pressure_summary = _format_pressure_summary(state)
    capability_summary = _format_capability_summary(actor)
    uncertainty_block = perception.get("uncertainty", {})
    contradictory_signals = "\n".join(
        f"- {item}" for item in uncertainty_block.get("contradictory_signals", [])
    ) or "No major contradictory signals detected."

    prompt = template.format(
        actor_name=actor.name,
        turn=state.turn,
        crisis_phase=state.crisis_phase,
        global_tension_band=f"{tension_band} ({global_tension:.2f})",
        active_conflicts=active,
        military_summary=_format_military_summary(self_perc),
        economic_summary=_format_economic_summary(self_perc),
        political_summary=_format_political_summary(self_perc),
        relationships_summary=relationships_block,
        recent_events=events_block,
        available_actions=available_block,
        pressure_summary=pressure_summary,
        capability_summary=capability_summary,
        uncertainty_level=uncertainty_block.get("level", "MEDIUM"),
        contradictory_signals=contradictory_signals,
    )

    if retry_feedback:
        prompt += f"\n\n---\n\n## RETRY — Previous Action Was Invalid\n\n{retry_feedback}"

    return prompt


# ── Canonical Action Tool Schema (OpenAI function format) ─────────────────────
# Provider-agnostic. AnthropicProvider renames 'parameters' → 'input_schema'.
# OpenRouterProvider uses this directly.

ACTION_TOOL_SCHEMA = {
    "name": "submit_action",
    "description": (
        "Submit your strategic decision for this turn. "
        "You MUST call this tool after completing your reasoning. "
        "Choose exactly one action_type from the available actions listed above."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "description": "The action type identifier (e.g., 'mobilize', 'negotiate', 'strike').",
                "enum": list(ACTION_REGISTRY.keys()),
            },
            "target_actor": {
                "type": "string",
                "description": "Short name of the target actor (e.g., 'PRC', 'USA'). Required for most non-self actions.",
            },
            "target_zone": {
                "type": "string",
                "description": "Zone identifier for territorial actions (e.g., 'taiwan_strait').",
            },
            "intensity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Intensity level of the action.",
            },
            "locality": {
                "type": "string",
                "description": "Optional theater locality or sub-zone (e.g., 'median_line', 'miyako_strait').",
            },
            "intent_annotation": {
                "type": "string",
                "description": "Optional short intent annotation for auditability.",
            },
            "communication_mode": {
                "type": "string",
                "description": "Optional signaling or communication mode (e.g., public_statement, private_channel).",
            },
            "rationale": {
                "type": "string",
                "description": "Brief justification for this action (1-2 sentences for the log).",
            },
        },
        "required": ["action_type", "rationale"],
    },
}


# ── LLM Decision Actor ────────────────────────────────────────────────────────

class LLMDecisionActor(ActorInterface):
    """
    LLM-driven decision actor for OSE.

    One instance per actor per simulation run.
    The system prompt (persona) is built once; decision prompts are built each turn.
    Provider is injected — swap AnthropicProvider for OpenRouterProvider at
    construction time without changing any other code.
    """

    def __init__(
        self,
        actor: Actor,
        doctrine_condition: str,
        run_id: str,
        provider: LLMProvider,
    ):
        self.actor = actor
        self.doctrine_condition = doctrine_condition
        self.run_id = run_id
        self._provider = provider
        self._validator = ActionValidator()
        self._persona_prompt = build_persona_prompt(actor, doctrine_condition)

    def decide(self, state: WorldState) -> Tuple[BaseAction, DecisionRecord]:
        """
        Run the full decision pipeline for one turn.
        Returns (validated_action, decision_record).
        On persistent failure after retries, falls back to HoldPositionAction.
        """
        state.ensure_derived_state()
        self.actor = state.actors[self.actor.short_name]
        perception, perception_metadata = build_perception_packet(self.actor, state)
        recent_events = self._extract_recent_events(state)

        decision_prompt = build_decision_prompt(
            self.actor, state, perception, recent_events
        )

        action, record = self._call_with_retry(
            state, perception, perception_metadata, decision_prompt, recent_events
        )
        return action, record

    def _call_with_retry(
        self,
        state: WorldState,
        perception: Dict[str, Any],
        perception_metadata: Dict[str, Any],
        initial_decision_prompt: str,
        recent_events: List[str],
    ) -> Tuple[BaseAction, DecisionRecord]:
        """
        Call the LLM, validate, retry up to MAX_RETRIES on invalid output.
        """
        decision_prompt = initial_decision_prompt
        reasoning_trace = ""
        raw_response = ""
        parsed_action_dict: Optional[Dict[str, Any]] = None
        retry_count = 0
        validation_result = "skipped"
        validation_errors: List[str] = []
        provider_usage: Dict[str, Any] = {}
        final_action: Optional[BaseAction] = None
        applied = False

        for attempt in range(MAX_RETRIES + 1):
            try:
                provider_result = self._provider.call(
                    system_prompt=self._persona_prompt,
                    user_message=decision_prompt,
                    action_tool_schema=ACTION_TOOL_SCHEMA,
                )
                reasoning_trace = provider_result.reasoning_trace
                tool_input = provider_result.action_dict
                raw_response = provider_result.raw_response
                provider_usage = provider_result.usage

                if tool_input is None:
                    validation_errors = ["LLM did not call submit_action tool."]
                    validation_result = "invalid" if attempt == 0 else "retry_invalid"
                    retry_count = attempt
                else:
                    tool_input["actor_id"] = self.actor.short_name
                    parsed_action_dict = tool_input

                    try:
                        candidate = parse_action_from_dict(tool_input)
                        val = self._validator.validate(candidate, state)

                        if val.is_valid:
                            final_action = candidate
                            validation_result = "valid" if attempt == 0 else "retry_valid"
                            validation_errors = []
                            applied = True
                            retry_count = attempt
                            break
                        else:
                            validation_errors = val.errors
                            validation_result = "invalid" if attempt == 0 else "retry_invalid"
                            retry_count = attempt

                            if attempt < MAX_RETRIES:
                                feedback = self._validator.format_error_feedback(val)
                                decision_prompt = build_decision_prompt(
                                    self.actor, state, perception,
                                    recent_events, retry_feedback=feedback
                                )

                    except (ValueError, Exception) as e:
                        validation_errors = [str(e)]
                        validation_result = "invalid" if attempt == 0 else "retry_invalid"
                        retry_count = attempt

            except Exception as e:
                validation_errors = [f"LLM call failed: {str(e)}"]
                validation_result = "invalid"
                retry_count = attempt
                break

        # Fallback on persistent failure
        if final_action is None:
            from engine.actions import HoldPositionAction
            final_action = HoldPositionAction(
                action_type="hold_position",
                actor_id=self.actor.short_name,
                rationale="Fallback: all retry attempts exhausted or failed validation.",
            )
            validation_result = "skipped"
            applied = True

        record = DecisionRecord(
            turn=state.turn,
            actor_short_name=self.actor.short_name,
            doctrine_condition=self.doctrine_condition,
            run_id=self.run_id,
            provider_name=self._provider.provider_name,
            model_id=self._provider.model_id,
            system_prompt=self._persona_prompt,
            perception_block=json.dumps(perception, indent=2),
            perception_metadata=perception_metadata,
            reasoning_trace=reasoning_trace,
            raw_llm_response=raw_response,
            parsed_action=parsed_action_dict,
            provider_usage=provider_usage,
            validation_result=validation_result,
            validation_errors=validation_errors,
            retry_count=retry_count,
            final_applied=applied,
            crisis_phase_at_decision=state.crisis_phase,
        )

        return final_action, record

    def _extract_recent_events(self, state: WorldState) -> List[str]:
        """Pull the last turn's events from the turn log for context injection."""
        if not state.turn_logs:
            return []
        last_log = state.turn_logs[-1]
        events = []
        if hasattr(last_log, "events_this_turn"):
            events += [e.description for e in last_log.events_this_turn]
        if hasattr(last_log, "cascade_events"):
            events += [f"[CASCADE] {e.description}" for e in last_log.cascade_events]
        return events
