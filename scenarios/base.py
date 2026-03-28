"""
ScenarioDefinition — abstract base class for all OSE scenarios.

A scenario provides:
  - initialize()         → WorldState (full initial state with actors + relationships)
  - get_turn_events()    → List[GlobalEvent] (pre-scripted injected events per turn)

Scenarios do NOT contain actor logic or resolution rules.
They are pure initial-condition + event-schedule definitions.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from world.state import WorldState
from world.events import GlobalEvent


class ScenarioDefinition(ABC):

    @abstractmethod
    def initialize(self) -> WorldState:
        """Build and return the full initial WorldState for this scenario."""
        pass

    @abstractmethod
    def get_turn_events(self, turn: int, state: WorldState) -> List[GlobalEvent]:
        """
        Return pre-scripted GlobalEvents to inject at the start of a given turn.
        These represent exogenous shocks the scenario designer controls.
        Return [] for turns with no scripted events.
        """
        pass
