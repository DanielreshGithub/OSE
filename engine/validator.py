"""
ActionValidator — rule-based validation of LLM-produced actions.

The validator is the firewall between LLM output and world state mutation.
It calls action.is_valid(state) and returns a structured result.
No LLM calls here — ever.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from engine.actions import BaseAction
from world.state import WorldState


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
    action: BaseAction


class ActionValidator:
    """
    Validates a typed action against the current world state.
    Called after parsing LLM output, before any world state mutation.
    """

    def validate(self, action: BaseAction, state: WorldState) -> ValidationResult:
        """
        Run is_valid() on the action and return a structured result.
        """
        valid, errors = action.is_valid(state)
        return ValidationResult(is_valid=valid, errors=errors, action=action)

    def format_error_feedback(self, result: ValidationResult) -> str:
        """
        Format validation errors as a feedback message to inject into retry prompt.
        Used by LLMDecisionActor when retrying after invalid action.
        """
        error_list = "\n".join(f"- {e}" for e in result.errors)
        return (
            f"Your previous action '{result.action.action_type}' was INVALID.\n"
            f"Validation errors:\n{error_list}\n\n"
            f"Choose a different action that avoids these errors."
        )
