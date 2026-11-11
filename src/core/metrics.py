from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from .agent import ArgumentativeAgent
from .models import BeliefRevision, InteractionRecord, rounded


class SocietyMetrics:
    """Transparent structural indicators; not validated social-science measures."""

    def compute(
        self,
        agents: dict[str, ArgumentativeAgent],
        interactions: list[InteractionRecord],
        revisions: list[BeliefRevision],
        cumulative_interactions: list[InteractionRecord],
        converged: bool = False,
    ) -> dict[str, Any]:
        active = [agent for agent in agents.values() if agent.belief_base]
        beliefs = [belief for agent in active for belief in agent.belief_base.values()]
        support_count = sum(row.action_type in {"SUPPORT", "PROVIDE_EVIDENCE"} for row in interactions)
        attack_count = sum(row.action_type in {"ATTACK", "CHALLENGE"} for row in interactions)
        directional_total = support_count + attack_count
        possible = len(active) * max(0, len(active) - 1)
        defensible = {
            agent.agent_id: sum(
                belief.activity == "active" and belief.agent_belief_status == "accepted"
                for belief in agent.belief_base.values()
            )
            for agent in active
        }
        dominant = min(
            (agent_id for agent_id, count in defensible.items() if count == max(defensible.values(), default=0)),
            default=None,
        )
        confidence_values = [belief.confidence for belief in beliefs]
        return {
            "active_agents": len(active),
            "active_interactions": len(interactions),
            "support_activity": support_count,
            "attack_activity": attack_count,
            "support_attack_ratio": rounded(support_count / attack_count) if attack_count else (1.0 if support_count else 0.0),
            "interaction_density": rounded(len(interactions) / possible) if possible else 0.0,
            "mean_internal_belief_confidence": rounded(mean(confidence_values)) if confidence_values else 0.0,
            "belief_revisions": len(revisions),
            "retractions": sum(row.new_status == "retracted" for row in revisions),
            "dominant_viewpoint_by_defensible_active_arguments": dominant,
            "defensible_active_arguments_by_agent": dict(sorted(defensible.items())),
            "conflict_intensity": rounded(attack_count / directional_total) if directional_total else 0.0,
            "disagreement_indicator": rounded(pstdev(confidence_values)) if len(confidence_values) > 1 else 0.0,
            "connected_components": self._components(active, cumulative_interactions),
            "convergence_indicator": converged,
            "modeling_note": "Các chỉ số là proxy cấu trúc minh bạch, không phải thước đo xã hội học đã được kiểm định.",
        }

    @staticmethod
    def _components(agents: list[ArgumentativeAgent], interactions: list[InteractionRecord]) -> int:
        ids = {agent.agent_id for agent in agents}
        adjacency = {agent_id: set() for agent_id in ids}
        for row in interactions:
            if row.target_agent in ids and row.actor_agent in ids:
                adjacency[row.actor_agent].add(row.target_agent)
                adjacency[row.target_agent].add(row.actor_agent)
        count = 0
        remaining = set(ids)
        while remaining:
            count += 1
            stack = [remaining.pop()]
            while stack:
                current = stack.pop()
                neighbors = adjacency[current] & remaining
                remaining -= neighbors
                stack.extend(sorted(neighbors))
        return count
