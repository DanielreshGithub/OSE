"""
ScenarioDefinition — abstract base class for all OSE scenarios.

The new scenario architecture keeps the same public engine contract:
  - initialize()      -> WorldState
  - get_turn_events() -> List[GlobalEvent]

Concrete scenarios may now implement open-ended, state-dependent event
generation, but they still expose the same interface to the engine.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import os
from typing import List
from world.state import WorldState
from world.events import GlobalEvent


class ScenarioDefinition(ABC):
    def __init__(self, seed: int | None = None):
        if seed is None:
            raw_seed = os.getenv("OSE_SCENARIO_SEED")
            seed = int(raw_seed) if raw_seed not in (None, "") else 0
        self.seed = int(seed)

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
