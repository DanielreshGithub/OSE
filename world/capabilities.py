"""
Capability models for OSE.

These models make actor capability constraints explicit and serializable.
They are intentionally bounded to normalized floats in [0.0, 1.0] so they can
be used both for prompt shaping and for engine-side feasibility checks.
"""
from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


CapabilityBand = Literal["LOW", "MEDIUM", "HIGH"]


class CapabilityVector(BaseModel):
    """
    Normalized actor capability vector.

    The fields are intentionally broad enough to support multiple scenarios,
    but concrete enough to avoid vague "power" scoring.
    """

    local_naval_projection: float = Field(ge=0.0, le=1.0)
    local_air_projection: float = Field(ge=0.0, le=1.0)
    missile_a2ad_capability: float = Field(ge=0.0, le=1.0)
    cyber_capability: float = Field(ge=0.0, le=1.0)
    intelligence_quality: float = Field(ge=0.0, le=1.0)
    economic_coercion_capacity: float = Field(ge=0.0, le=1.0)
    alliance_leverage: float = Field(ge=0.0, le=1.0)
    logistics_endurance: float = Field(ge=0.0, le=1.0)
    domestic_stability: float = Field(ge=0.0, le=1.0)
    war_aversion: float = Field(ge=0.0, le=1.0)
    escalation_tolerance: float = Field(ge=0.0, le=1.0)
    bureaucratic_flexibility: float = Field(ge=0.0, le=1.0)
    signaling_credibility: float = Field(ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}

    def clamp(self) -> "CapabilityVector":
        """Clamp any runtime mutation back into range."""
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if isinstance(value, float):
                setattr(self, field_name, max(0.0, min(1.0, value)))
        return self

    def band(self, value: float) -> CapabilityBand:
        """Convert a normalized float to a qualitative band."""
        if value >= 0.65:
            return "HIGH"
        if value >= 0.35:
            return "MEDIUM"
        return "LOW"

    def as_bands(self) -> Dict[str, CapabilityBand]:
        """Return a prompt-friendly banded view of the capability vector."""
        return {
            field_name: self.band(getattr(self, field_name))
            for field_name in self.__class__.model_fields
        }

    def as_numeric(self) -> Dict[str, float]:
        """Return a plain numeric mapping for engine-side use."""
        return {
            field_name: float(getattr(self, field_name))
            for field_name in self.__class__.model_fields
        }

    def describe(self) -> Dict[str, Any]:
        """
        Return a compact structured summary suitable for logging.
        The caller can serialize this directly.
        """
        return {
            "numeric": self.as_numeric(),
            "bands": self.as_bands(),
        }
