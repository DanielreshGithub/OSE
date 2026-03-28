"""
RelationshipGraph — thin query wrapper over WorldState.relationships.

Provides named query methods without requiring NetworkX as a hard dependency.
All queries are O(n) over the relationship list; for 4–8 actors this is
perfectly fine. NetworkX export is available optionally for post-hoc
graph-theoretic analysis (alliance clustering, centrality measures, etc.).
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from world.state import BilateralRelationship, WorldState


class RelationshipGraph:
    """
    Thin query wrapper over WorldState.relationships.
    Provides named query methods without requiring NetworkX as a hard dependency.
    NetworkX export is available optionally for analysis.
    """

    def __init__(self, state: WorldState):
        self._state = state
        self._index: Dict[Tuple[str, str], BilateralRelationship] = {
            (r.from_actor, r.to_actor): r for r in state.relationships
        }

    def get(self, from_actor: str, to_actor: str) -> Optional[BilateralRelationship]:
        return self._index.get((from_actor, to_actor))

    def get_allies(self, actor: str, min_strength: float = 0.5) -> List[str]:
        return [
            r.to_actor for r in self._state.relationships
            if r.from_actor == actor
            and r.relationship_type in ("ally", "partner")
            and r.alliance_strength >= min_strength
        ]

    def get_adversaries(self, actor: str) -> List[str]:
        return [
            r.to_actor for r in self._state.relationships
            if r.from_actor == actor
            and r.relationship_type in ("adversary", "hostile")
        ]

    def get_threat_perception(self, perceiver: str, target: str) -> float:
        rel = self.get(perceiver, target)
        return rel.threat_perception if rel else 0.0

    def get_deterrence_credibility(self, believer: str, actor: str) -> float:
        """How credible does 'believer' find 'actor's' commitments?"""
        rel = self.get(believer, actor)
        return rel.deterrence_credibility if rel else 0.5

    def all_relationships_for(self, actor: str) -> List[BilateralRelationship]:
        return [r for r in self._state.relationships if r.from_actor == actor]

    def to_networkx(self):
        """Optional: export to NetworkX DiGraph for post-hoc analysis."""
        try:
            import networkx as nx
            G = nx.DiGraph()
            for r in self._state.relationships:
                G.add_edge(
                    r.from_actor, r.to_actor,
                    **r.model_dump(exclude={"from_actor", "to_actor"})
                )
            return G
        except ImportError:
            raise RuntimeError(
                "networkx not installed. Install with: uv add networkx"
            )
