"""
LLMDecisionActor — the core OSE actor implementation.

Pipeline per turn:
  1. build_perception()    — filter + noise world state for this actor
  2. build_persona_prompt()— stable system prompt (cached by Anthropic)
  3. build_decision_prompt()— per-turn user prompt with situation + schema
  4. LLM call via tool_use — forces structured JSON action output
  5. parse + validate      — ActionValidator; retry up to MAX_RETRIES on failure
  6. Return (action, DecisionRecord)

The LLM never touches world state directly.
The validator is the firewall — pure rule-based, no LLM.
"""
from __future__ import annotations

import os
import json
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import anthropic
from dotenv import load_dotenv

from world.state import Actor, WorldState, BilateralRelationship
from world.events import DecisionRecord
from engine.actions import (
    BaseAction, ACTION_REGISTRY, parse_action_from_dict,
    get_available_actions_for,
)
from engine.validator import ActionValidator
from actors.base import ActorInterface
from actors.persona import build_persona_prompt

load_dotenv()

MAX_RETRIES = 2
MODEL = "claude-sonnet-4-6"

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


def _to_band_with_noise(value: float, noise_scale: float) -> str:
    """
    Add Gaussian noise proportional to (1 - information_quality) before
    converting to band. This is where Jervis's misperception thesis lives —
    actors with poor intel see degraded, noisy assessments of adversaries.
    """
    if noise_scale > 0.0:
        noise = random.gauss(0, noise_scale)
        value = max(0.0, min(1.0, value + noise))
    return _to_band(value)


# ── Perception Filter ─────────────────────────────────────────────────────────

def build_perception(actor: Actor, state: WorldState) -> Dict[str, Any]:
    """
    Build an actor-specific, noisy view of the world state.

    - Own resources: seen accurately (noise_scale = 0)
    - Ally resources: slight noise (noise_scale = 0.05)
    - Adversary resources: noise proportional to (1 - information_quality)
    - Neutral/competitor: medium noise (noise_scale = 0.15)

    Returns a structured dict used to populate the decision prompt.
    """
    noise_base = 1.0 - actor.information_quality
    allies = set(state.get_allies(actor.short_name))
    adversaries = set(state.get_adversaries(actor.short_name))

    perception: Dict[str, Any] = {
        "self": _perceive_actor(state.actors[actor.short_name], noise_scale=0.0),
        "others": {},
        "relationships": [],
        "systemic": {
            "semiconductor_supply_chain": _to_band(state.systemic.semiconductor_supply_chain_integrity),
            "global_shipping_disruption": _to_band(state.systemic.global_shipping_disruption),
            "energy_market_volatility": _to_band(state.systemic.energy_market_volatility),
            "alliance_system_cohesion": _to_band(state.systemic.alliance_system_cohesion),
        },
    }

    for name, other in state.actors.items():
        if name == actor.short_name:
            continue
        if name in allies:
            noise = 0.05
        elif name in adversaries:
            noise = noise_base * 0.4
        else:
            noise = 0.15
        perception["others"][name] = _perceive_actor(other, noise_scale=noise)

    for rel in state.relationships:
        if rel.from_actor == actor.short_name:
            perception["relationships"].append({
                "with": rel.to_actor,
                "type": rel.relationship_type,
                "trust": _to_band(rel.trust_score),
                "alliance_strength": _to_band(rel.alliance_strength),
                "threat_perception": _to_band(rel.threat_perception),
                "deterrence_credibility": _to_band(rel.deterrence_credibility),
            })

    return perception


def _perceive_actor(actor: Actor, noise_scale: float) -> Dict[str, str]:
    """Convert an actor's resources to qualitative bands with optional noise."""
    m = actor.military
    e = actor.economic
    p = actor.political

    def b(val: float) -> str:
        return _to_band_with_noise(val, noise_scale)

    return {
        "conventional_forces": b(m.conventional_forces),
        "naval_power": b(m.naval_power),
        "air_superiority": b(m.air_superiority),
        "nuclear_capability": b(m.nuclear_capability),
        "readiness": b(m.readiness),
        "amphibious_capacity": b(m.amphibious_capacity),
        "a2ad_effectiveness": b(m.a2ad_effectiveness),
        "gdp_strength": b(e.gdp_strength),
        "foreign_reserves": b(e.foreign_reserves),
        "energy_independence": b(e.energy_independence),
        "trade_openness": b(e.trade_openness),
        "industrial_capacity": b(e.industrial_capacity),
        "domestic_stability": b(p.domestic_stability),
        "regime_legitimacy": b(p.regime_legitimacy),
        "international_standing": b(p.international_standing),
        "decision_unity": b(p.decision_unity),
        "casualty_tolerance": b(p.casualty_tolerance),
        "posture": actor.current_posture,
    }


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
            f"Readiness: {other['readiness']}"
        )
    return "\n".join(lines)


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

    prompt = template.format(
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
    )

    if retry_feedback:
        prompt += f"\n\n---\n\n## RETRY — Previous Action Was Invalid\n\n{retry_feedback}"

    return prompt


# ── Anthropic Tool Schema ─────────────────────────────────────────────────────

ACTION_TOOL = {
    "name": "submit_action",
    "description": (
        "Submit your strategic decision for this turn. "
        "You MUST call this tool after completing your reasoning. "
        "Choose exactly one action_type from the available actions listed above."
    ),
    "input_schema": {
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
    """

    def __init__(
        self,
        actor: Actor,
        doctrine_condition: str,
        run_id: str,
    ):
        self.actor = actor
        self.doctrine_condition = doctrine_condition
        self.run_id = run_id
        self._validator = ActionValidator()
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._persona_prompt = build_persona_prompt(actor, doctrine_condition)

    def decide(self, state: WorldState) -> Tuple[BaseAction, DecisionRecord]:
        """
        Run the full decision pipeline for one turn.
        Returns (validated_action, decision_record).
        On persistent failure after retries, falls back to HoldPositionAction.
        """
        perception = build_perception(self.actor, state)
        recent_events = self._extract_recent_events(state)

        decision_prompt = build_decision_prompt(
            self.actor, state, perception, recent_events
        )

        action, record = self._call_with_retry(
            state, perception, decision_prompt, recent_events
        )
        return action, record

    def _call_with_retry(
        self,
        state: WorldState,
        perception: Dict[str, Any],
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
        final_action: Optional[BaseAction] = None
        applied = False

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=[
                        {
                            "type": "text",
                            "text": self._persona_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": decision_prompt}],
                    tools=[ACTION_TOOL],
                    tool_choice={"type": "auto"},
                    temperature=0,
                )

                # Extract reasoning trace (text blocks) and tool call
                reasoning_parts = []
                tool_input: Optional[Dict[str, Any]] = None

                for block in response.content:
                    if block.type == "text":
                        reasoning_parts.append(block.text)
                    elif block.type == "tool_use" and block.name == "submit_action":
                        tool_input = block.input

                reasoning_trace = "\n".join(reasoning_parts)
                raw_response = str(response.content)

                # Safety net: if model skipped text blocks (e.g., model went straight
                # to tool call despite tool_choice="auto"), pull rationale from tool input
                if not reasoning_trace and tool_input:
                    reasoning_trace = tool_input.get("rationale", "")

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
            system_prompt=self._persona_prompt,
            perception_block=json.dumps(perception, indent=2),
            reasoning_trace=reasoning_trace,
            raw_llm_response=raw_response,
            parsed_action=parsed_action_dict,
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
