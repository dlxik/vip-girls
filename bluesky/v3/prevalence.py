from __future__ import annotations

from statistics import mean
from typing import Any

from bluesky.v2.models import rounded


class StructuralPrevalenceCalculator:
    """Computes S_i as a structural proxy, never as real public popularity."""

    def compute(
        self,
        agent_states: dict[str, dict[str, Any]],
        cumulative_interactions: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        argument_catalog: dict[str, Any],
        timestamp_order: list[str],
        current_timestamp: str,
    ) -> dict[str, Any]:
        active_states = {
            agent_id: state for agent_id, state in agent_states.items()
            if state["belief_states"]
        }
        n_agents = len(active_states)
        rank = {timestamp: index for index, timestamp in enumerate(timestamp_order)}
        current_rank = rank[current_timestamp]
        raw: dict[str, dict[str, float]] = {}
        for agent_id, state in sorted(active_states.items()):
            beliefs = list(state["belief_states"].values())
            owned = {row["argument_id"] for row in beliefs}
            active_arguments = sum(row["activity"] == "active" for row in beliefs)
            unique_sources = set(state["evidence_base"])
            source_types = {
                source["source_type"]
                for argument_id in owned
                for source in argument_catalog[argument_id].get("sources", [])
            }
            persistence_values = []
            for argument_id in owned:
                introduced = argument_catalog[argument_id]["introduced_at"]
                persistence_values.append((current_rank - rank[introduced] + 1) / len(timestamp_order))
            incoming_support = sum(
                row["relation_type"] == "support" and row["target"] in owned
                for row in relations
            )
            outgoing_influence = sum(
                row.get("actor_agent") == agent_id and row.get("target_agent") is not None
                for row in cumulative_interactions
            )
            peers = {
                row["target_agent"] if row["actor_agent"] == agent_id else row["actor_agent"]
                for row in cumulative_interactions
                if row.get("target_agent")
                and agent_id in {row["actor_agent"], row["target_agent"]}
            }
            raw[agent_id] = {
                "active_arguments": float(active_arguments),
                "unique_sources": float(len(unique_sources)),
                "persistence": mean(persistence_values) if persistence_values else 0.0,
                "source_diversity": len(source_types) / 4.0,
                "incoming_support": float(incoming_support),
                "outgoing_influence": float(outgoing_influence),
                "interaction_reach": len(peers) / max(1, n_agents - 1),
            }

        maxima = {
            field: max((row[field] for row in raw.values()), default=0.0)
            for field in ("active_arguments", "unique_sources", "incoming_support", "outgoing_influence")
        }
        results: dict[str, dict[str, Any]] = {}
        for agent_id, row in raw.items():
            active_norm = row["active_arguments"] / maxima["active_arguments"] if maxima["active_arguments"] else 0.0
            source_norm = row["unique_sources"] / maxima["unique_sources"] if maxima["unique_sources"] else 0.0
            support_norm = row["incoming_support"] / maxima["incoming_support"] if maxima["incoming_support"] else 0.0
            influence_norm = row["outgoing_influence"] / maxima["outgoing_influence"] if maxima["outgoing_influence"] else 0.0
            prevalence = (
                0.25 * active_norm
                + 0.20 * source_norm
                + 0.15 * row["persistence"]
                + 0.15 * support_norm
                + 0.15 * influence_norm
                + 0.10 * row["interaction_reach"]
            )
            visibility = 0.55 * influence_norm + 0.45 * row["interaction_reach"]
            results[agent_id] = {
                "structural_prevalence": rounded(prevalence),
                "visibility_proxy": rounded(visibility),
                "persistence": rounded(row["persistence"]),
                "source_diversity": rounded(row["source_diversity"]),
                "interaction_reach": rounded(row["interaction_reach"]),
                "components": {
                    "active_argument_norm": rounded(active_norm),
                    "unique_source_norm": rounded(source_norm),
                    "incoming_support_norm": rounded(support_norm),
                    "outgoing_influence_norm": rounded(influence_norm),
                },
            }
        return {
            "by_agent": results,
            "formula": "0.25 active arguments + 0.20 unique sources + 0.15 temporal persistence + 0.15 incoming support + 0.15 outgoing influence + 0.10 interaction reach (normalized)",
            "interpretation": "Structural visibility/influence inside the modeled argument society.",
            "limitation": "These are structural proxies, not measurements of real public support.",
            "real_social_prevalence": None,
        }
