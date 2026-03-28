"""
ActorInterface — abstract base class for all OSE decision agents.

In v0.1, the only concrete implementation is LLMDecisionActor.
This interface exists to allow future scripted/rule-based actors
for testing or baseline comparison without changing the engine.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from world.state import WorldState
    from world.events import DecisionRecord
    from engine.actions import BaseAction


class ActorInterface(ABC):
    """Abstract base class for all OSE decision agents."""

    @abstractmethod
    def decide(self, state: "WorldState") -> Tuple["BaseAction", "DecisionRecord"]:
        """
        Given the current world state, return a valid typed action
        and the full decision record for logging.
        """
        pass
