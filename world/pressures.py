"""
Pressure models for OSE.

Pressures are derived, stateful indicators that sit between raw world state and
event generation. They are intentionally explicit so they can be logged,
replayed, and inspected during analysis.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


PressureBand = Literal["LOW", "MEDIUM", "HIGH"]
PressureSource = Literal["state", "event", "action", "cascade", "scenario", "inference"]


class PressureContribution(BaseModel):
    """One explainable reason a pressure dimension changed."""

    dimension: str
    delta: float = Field(ge=-1.0, le=1.0)
    source: PressureSource
    reason: str
    actor_short_name: Optional[str] = None
    turn: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class PressureState(BaseModel):
    """
    Normalized pressure state for the current scenario turn.

    These fields are scenario-agnostic. Scenario templates can reweight them
    or layer on additional logic without changing the core engine contract.
    """

    military_pressure: float = Field(ge=0.0, le=1.0)
    diplomatic_pressure: float = Field(ge=0.0, le=1.0)
    alliance_pressure: float = Field(ge=0.0, le=1.0)
    domestic_pressure: float = Field(ge=0.0, le=1.0)
    economic_pressure: float = Field(ge=0.0, le=1.0)
    informational_pressure: float = Field(ge=0.0, le=1.0)
    crisis_instability: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)

    turn: int = 0
    scenario_id: str = ""
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    contributions: List[PressureContribution] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    def clamp(self) -> "PressureState":
        """Clamp runtime mutations back into range."""
        for field_name in (
            "military_pressure",
            "diplomatic_pressure",
            "alliance_pressure",
            "domestic_pressure",
            "economic_pressure",
            "informational_pressure",
            "crisis_instability",
            "uncertainty",
        ):
            value = getattr(self, field_name)
            setattr(self, field_name, max(0.0, min(1.0, float(value))))
        return self

    def band(self, value: float) -> PressureBand:
        """Convert a normalized float to a qualitative band."""
        if value >= 0.65:
            return "HIGH"
        if value >= 0.35:
            return "MEDIUM"
        return "LOW"

    def as_bands(self) -> Dict[str, PressureBand]:
        """Return a compact qualitative view for prompts and logs."""
        return {
            "military_pressure": self.band(self.military_pressure),
            "diplomatic_pressure": self.band(self.diplomatic_pressure),
            "alliance_pressure": self.band(self.alliance_pressure),
            "domestic_pressure": self.band(self.domestic_pressure),
            "economic_pressure": self.band(self.economic_pressure),
            "informational_pressure": self.band(self.informational_pressure),
            "crisis_instability": self.band(self.crisis_instability),
            "uncertainty": self.band(self.uncertainty),
        }

    def as_numeric(self) -> Dict[str, float]:
        """Return a plain numeric mapping for engine-side use."""
        return {
            "military_pressure": float(self.military_pressure),
            "diplomatic_pressure": float(self.diplomatic_pressure),
            "alliance_pressure": float(self.alliance_pressure),
            "domestic_pressure": float(self.domestic_pressure),
            "economic_pressure": float(self.economic_pressure),
            "informational_pressure": float(self.informational_pressure),
            "crisis_instability": float(self.crisis_instability),
            "uncertainty": float(self.uncertainty),
        }

    def to_trace(self) -> Dict[str, Any]:
        """Return a serialization-friendly audit trace."""
        return {
            "turn": self.turn,
            "scenario_id": self.scenario_id,
            "values": self.as_numeric(),
            "bands": self.as_bands(),
            "contributions": [c.model_dump() for c in self.contributions],
            "metadata": dict(self.metadata),
        }


class PressureDelta(BaseModel):
    """A deterministic change to one or more pressure dimensions."""

    military_pressure: float = 0.0
    diplomatic_pressure: float = 0.0
    alliance_pressure: float = 0.0
    domestic_pressure: float = 0.0
    economic_pressure: float = 0.0
    informational_pressure: float = 0.0
    crisis_instability: float = 0.0
    uncertainty: float = 0.0

    source: PressureSource = "inference"
    reason: str = ""
    actor_short_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    def as_numeric(self) -> Dict[str, float]:
        return {
            "military_pressure": float(self.military_pressure),
            "diplomatic_pressure": float(self.diplomatic_pressure),
            "alliance_pressure": float(self.alliance_pressure),
            "domestic_pressure": float(self.domestic_pressure),
            "economic_pressure": float(self.economic_pressure),
            "informational_pressure": float(self.informational_pressure),
            "crisis_instability": float(self.crisis_instability),
            "uncertainty": float(self.uncertainty),
        }


def apply_pressure_delta(state: PressureState, delta: PressureDelta, turn: Optional[int] = None) -> PressureState:
    """Apply a delta to a pressure state and return the mutated state."""
    for field_name, field_delta in delta.as_numeric().items():
        if field_delta == 0.0:
            continue
        current = float(getattr(state, field_name))
        setattr(state, field_name, max(0.0, min(1.0, current + field_delta)))
        state.contributions.append(
            PressureContribution(
                dimension=field_name,
                delta=field_delta,
                source=delta.source,
                reason=delta.reason,
                actor_short_name=delta.actor_short_name,
                turn=turn,
                metadata=delta.metadata,
            )
        )
    state.last_updated = datetime.utcnow()
    return state.clamp()


def empty_pressure_state(turn: int = 0, scenario_id: str = "") -> PressureState:
    """Construct a zeroed pressure state."""
    return PressureState(
        military_pressure=0.0,
        diplomatic_pressure=0.0,
        alliance_pressure=0.0,
        domestic_pressure=0.0,
        economic_pressure=0.0,
        informational_pressure=0.0,
        crisis_instability=0.0,
        uncertainty=0.0,
        turn=turn,
        scenario_id=scenario_id,
    )


class PressureModel(BaseModel):
    """
    Stateful pressure tracker.

    This is intentionally simple: callers supply a PressureDelta each turn,
    and the model keeps the current state plus a replayable history.
    """

    state: PressureState = Field(default_factory=empty_pressure_state)
    history: List[PressureState] = Field(default_factory=list)
    seed: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    def advance(self, delta: PressureDelta, turn: Optional[int] = None) -> PressureState:
        """Apply a delta, persist a snapshot, and return the new state."""
        self.history.append(self.state.model_copy(deep=True))
        self.state = apply_pressure_delta(self.state, delta, turn=turn)
        if turn is not None:
            self.state.turn = turn
        return self.state

    def snapshot(self) -> Dict[str, Any]:
        """Return a replay-friendly snapshot of the current pressure model."""
        return {
            "state": self.state.to_trace(),
            "history": [item.to_trace() for item in self.history],
            "seed": self.seed,
            "metadata": dict(self.metadata),
        }

    def reset(self, state: Optional[PressureState] = None) -> "PressureModel":
        """Reset the model to a fresh state while preserving configuration."""
        self.history = []
        self.state = state.model_copy(deep=True) if state is not None else empty_pressure_state()
        return self
