from __future__ import annotations

from typing import Any

from .agent import ArgumentativeAgent
from .models import AgentObservation, InteractionRecord


class ObservationBuilder:
    def __init__(self, argument_owner: dict[str, str]) -> None:
        self.argument_owner = argument_owner

    def build(
        self,
        agent: ArgumentativeAgent,
        snapshot: dict[str, Any],
        deliberation_step: int,
        prior_interactions: list[InteractionRecord],
    ) -> AgentObservation:
        timestamp = snapshot["timestamp"]["timestamp_id"]
        owned = set(agent.belief_base)
        relevant_relations = [
            relation for relation in snapshot["relations"]
            if relation["source"] in owned or relation["target"] in owned
        ]
        incoming_support = [
            relation for relation in relevant_relations
            if relation["target"] in owned and relation["relation_type"] == "support"
        ]
        incoming_attacks = [
            relation for relation in relevant_relations
            if relation["target"] in owned and relation["relation_type"] == "attack"
        ]
        new_arguments = [
            argument["id"] for argument in snapshot["arguments"]
            if argument["id"] in owned and argument["newly_introduced"] and deliberation_step == 0
        ]
        source_ids: list[str] = []
        if deliberation_step == 0:
            by_id = {argument["id"]: argument for argument in snapshot["arguments"]}
            for argument_id in new_arguments:
                for source_id in by_id[argument_id]["source_ids"]:
                    if source_id not in source_ids:
                        source_ids.append(source_id)
            for relation in relevant_relations:
                if relation["newly_introduced"]:
                    for source_id in relation["evidence_sources"]:
                        if source_id not in source_ids:
                            source_ids.append(source_id)
        actions = [
            item.to_dict() for item in prior_interactions
            if item.target_agent == agent.agent_id or item.actor_agent == agent.agent_id
        ]
        changes = [
            change for change in snapshot["changes"]["changed_statuses"]
            if change["arg_id"] in owned
        ] if deliberation_step == 0 else []
        observation = AgentObservation(
            observation_id=f"OBS-{timestamp}-k{deliberation_step}-{agent.agent_id}",
            agent_id=agent.agent_id,
            timestamp=timestamp,
            deliberation_step=deliberation_step,
            newly_introduced_arguments=sorted(new_arguments),
            newly_introduced_evidence=sorted(source_ids),
            incoming_support=sorted(incoming_support, key=lambda row: row["id"]),
            incoming_attacks=sorted(incoming_attacks, key=lambda row: row["id"]),
            other_agent_actions=sorted(actions, key=lambda row: row["action_id"]),
            canonical_status_changes=sorted(changes, key=lambda row: row["arg_id"]),
            source_status_changes=[],
            current_temporal_context={
                "timestamp_id": timestamp,
                "label": snapshot["timestamp"]["label"],
                "event": snapshot["timestamp"]["event"],
                "real_time_not_simulation_round": True,
            },
            relevant_relations=sorted(relevant_relations, key=lambda row: row["id"]),
            provenance={
                "argument_ids": sorted(owned),
                "relation_ids": sorted(row["id"] for row in relevant_relations),
                "source_ids": sorted(set(source_ids)),
            },
        )
        agent.observations.append(observation.to_dict())
        return observation
