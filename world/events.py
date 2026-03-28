"""
Event and logging data models for the Omni-Simulation Engine.

These models record everything that happens during a simulation run:
injected events, actor decisions (with full prompt/reasoning traces),
per-turn logs, and top-level run records. The goal is full replay capability:
re-feeding a stored system_prompt + perception_block with temperature=0
should reproduce the same action.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

EventCategory = Literal[
    "military", "diplomatic", "economic", "information", "natural", "cascade", "injected"
]

ValidationResult = Literal["valid", "invalid", "retry_valid", "retry_invalid", "skipped"]


class GlobalEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn: int
    category: EventCategory
    description: str
    source: Literal["system", "actor", "cascade", "injected", "generated"]
    caused_by_actor: Optional[str] = None   # short_name
    affected_actors: List[str] = Field(default_factory=list)
    event_family: Optional[str] = None
    eligibility_reasons: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured metadata explaining why this event was eligible and selected"
    )
    world_state_delta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable description of what changed"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    """Complete log of one actor's decision in one turn."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn: int
    actor_short_name: str
    doctrine_condition: str   # "realist" | "liberal" | "org_process" | "baseline"
    run_id: str
    provider_name: str = "unknown"
    model_id: str = "unknown"

    # Prompt inputs (stored for replay)
    system_prompt: str
    perception_block: str
    perception_metadata: Dict[str, Any] = Field(default_factory=dict)

    # LLM outputs
    reasoning_trace: str          # Model-visible rationale text captured for replay/scoring
    raw_llm_response: str         # Unparsed LLM response
    parsed_action: Optional[Dict[str, Any]] = None
    provider_usage: Dict[str, Any] = Field(default_factory=dict)

    # Validation
    validation_result: ValidationResult
    validation_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    final_applied: bool = False

    # Scoring (populated by fidelity scorer after the fact)
    doctrine_language_score: Optional[float] = None   # 0-1
    doctrine_logic_score: Optional[float] = None       # 0-1
    doctrine_consistent_decision: Optional[bool] = None
    contamination_flag: Optional[bool] = None

    # Crisis phase at time of decision (for pressure robustness analysis)
    crisis_phase_at_decision: str = "peacetime"

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TurnLog(BaseModel):
    run_id: str
    turn: int
    doctrine_condition: str
    crisis_phase: str
    global_tension: float
    pressure_before: Dict[str, Any] = Field(default_factory=dict)
    pressure_after: Dict[str, Any] = Field(default_factory=dict)
    events_this_turn: List[GlobalEvent] = Field(default_factory=list)
    decisions: List[DecisionRecord] = Field(default_factory=list)
    cascade_events: List[GlobalEvent] = Field(default_factory=list)
    event_generation_audit: List[Dict[str, Any]] = Field(default_factory=list)
    perception_packets: Dict[str, Any] = Field(default_factory=dict)
    state_mutations: List[Dict[str, Any]] = Field(default_factory=list)
    terminal_checks: Dict[str, Any] = Field(default_factory=dict)
    world_state_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON serialization of WorldState at turn end"
    )
    terminal_condition_met: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RunRecord(BaseModel):
    """Top-level record for one complete simulation run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str
    doctrine_condition: str
    provider_name: str = "unknown"
    model_id: str = "unknown"
    run_number: int
    seed: Optional[int] = None
    total_turns: int
    final_crisis_phase: str
    outcome_classification: Optional[str] = None   # deterrence_success | defense_success | frozen | failure
    final_global_tension: float
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    completed: bool = False
