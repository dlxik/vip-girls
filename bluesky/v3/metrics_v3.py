from __future__ import annotations

from itertools import combinations
from statistics import mean
from typing import Any

from bluesky.v2.models import rounded


def weak_components(agent_ids: set[str], interactions: list[dict[str, Any]]) -> list[list[str]]:
    adjacency = {agent_id: set() for agent_id in agent_ids}
    for row in interactions:
        source, target = row.get("actor_agent"), row.get("target_agent")
        if source in agent_ids and target in agent_ids:
            adjacency[source].add(target)
            adjacency[target].add(source)
    components: list[list[str]] = []
    remaining = set(agent_ids)
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack = [seed]
        component = {seed}
        while stack:
            current = stack.pop()
            neighbors = adjacency[current] & remaining
            remaining -= neighbors
            component |= neighbors
            stack.extend(sorted(neighbors))
        components.append(sorted(component))
    return sorted(components, key=lambda row: (len(row), row))


class SocietyMetricsV3:
    def compute(
        self,
        agent_states: dict[str, dict[str, Any]],
        interactions: list[dict[str, Any]],
        cumulative_interactions: list[dict[str, Any]],
        v2_metrics: dict[str, Any],
        semantics: dict[str, Any],
        viewpoint_dynamics: dict[str, Any],
        prevalence: dict[str, Any],
    ) -> dict[str, Any]:
        active = {
            agent_id: state for agent_id, state in agent_states.items()
            if state["belief_states"]
        }
        positions: dict[str, float] = {}
        for agent_id, state in active.items():
            beliefs = list(state["belief_states"].values())
            positions[agent_id] = mean(row["confidence"] for row in beliefs)
        pair_distances = [abs(positions[a] - positions[b]) for a, b in combinations(sorted(positions), 2)]
        polarization = mean(pair_distances) if pair_distances else 0.0
        attack = sum(row["action_type"] in {"ATTACK", "CHALLENGE", "CHALLENGE_INVALID_GROUNDING"} for row in interactions)
        support = sum(row["action_type"] in {"SUPPORT", "PROVIDE_EVIDENCE", "CLARIFY_NORM", "CLARIFY_AUTHORITY"} for row in interactions)
        conflict_intensity = attack / (attack + support) if attack + support else 0.0
        consensus_proxy = 0.55 * (1.0 - polarization) + 0.45 * (1.0 - conflict_intensity)
        cohesion_values = [row["cohesion"] for row in viewpoint_dynamics["cohesion_by_agent"].values()]
        convergence_proxy = 0.45 * consensus_proxy + 0.35 * (mean(cohesion_values) if cohesion_values else 0.0) + 0.20 * (1.0 - conflict_intensity)
        components = weak_components(set(active), cumulative_interactions)
        isolated = [component[0] for component in components if len(component) == 1]
        fragmentation = (len(components) - 1) / max(1, len(active) - 1) if active else 0.0
        prevalence_by_agent = prevalence["by_agent"]
        dominant = min(
            (
                agent_id for agent_id, row in prevalence_by_agent.items()
                if row["structural_prevalence"] == max(
                    (item["structural_prevalence"] for item in prevalence_by_agent.values()),
                    default=0.0,
                )
            ),
            default=None,
        )
        semantic_status_counts = {"accepted": 0, "rejected": 0, "undecided": 0}
        for row in semantics["results"].values():
            semantic_status_counts[row["semantic_status"]] += 1
        return {
            "dominant_viewpoint": dominant,
            "dominance_basis": "maximum structural_prevalence; lexicographic tie-break",
            "viewpoint_cohesion": viewpoint_dynamics["cohesion_by_agent"],
            "structural_prevalence": prevalence_by_agent,
            "convergence_proxy": rounded(convergence_proxy),
            "consensus_proxy": rounded(consensus_proxy),
            "simulation_convergence": bool(v2_metrics["convergence_indicator"]),
            "convergence_consensus_separated": True,
            "fragmentation_proxy": rounded(fragmentation),
            "weakly_connected_components": components,
            "disconnected_component_count": len(components),
            "isolated_agents": isolated,
            "persistent_subcommunities": [row for row in components if len(row) > 1],
            "polarization_proxy": rounded(polarization),
            "conflict_intensity": rounded(conflict_intensity),
            "split_candidates": viewpoint_dynamics["split_candidates"],
            "merge_candidates": viewpoint_dynamics["merge_candidates"],
            "semantic_status_counts": semantic_status_counts,
            "formulas": {
                "polarization_proxy": "mean pairwise absolute distance between agent mean confidence",
                "consensus_proxy": "0.55*(1-polarization) + 0.45*(1-current conflict intensity)",
                "convergence_proxy": "0.45*consensus + 0.35*mean cohesion + 0.20*(1-conflict)",
                "fragmentation_proxy": "(weak components-1)/(active agents-1)",
            },
            "limitations": {
                "consensus": "Structural similarity only; never equated with social consensus.",
                "polarization": "Confidence-distance proxy, not a validated social-science measure.",
                "fragmentation": "Interaction-graph structure within the simulation only.",
            },
        }
