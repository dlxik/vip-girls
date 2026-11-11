from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from core.models import rounded

from .models import ArgumentSubAgent, ViewpointMacroAgent


def argument_agent_id(argument_id: str) -> str:
    suffix = argument_id.removeprefix("CTQ-")
    return f"ARG-{suffix}"


class AgentHierarchy:
    """Immutable ownership plus mutable argument-level runtime state."""

    def __init__(self, data: dict[str, Any], argument_catalog: dict[str, Any]) -> None:
        self.mapping = data["viewpoint_mapping"]
        self.catalog = argument_catalog
        self.owners: dict[str, list[str]] = {}
        for row in self.mapping["viewpoints"]:
            for argument_id in row["argument_ids"]:
                self.owners.setdefault(argument_id, []).append(row["viewpoint_id"])
        if set(self.owners) != set(argument_catalog):
            raise ValueError("Hierarchy phải phủ mọi canonical argument")
        self.primary_owner = {
            argument_id: owners[0] for argument_id, owners in self.owners.items()
        }
        self.subagents = {
            argument_id: ArgumentSubAgent(
                agent_id=argument_agent_id(argument_id),
                argument_id=argument_id,
                parent_viewpoint_ids=list(self.owners[argument_id]),
                argument_type=argument_catalog[argument_id]["arg_type"],
                belief_status="undecided",
                confidence=0.5,
                active=False,
                introduced_at=argument_catalog[argument_id]["introduced_at"],
                source_ids=list(argument_catalog[argument_id]["source_ids"]),
                evidence_ids=list(argument_catalog[argument_id]["source_ids"]),
            )
            for argument_id in sorted(argument_catalog)
        }

    def sync_from_society_step(self, step: dict[str, Any]) -> None:
        for viewpoint_id, viewpoint_state in step["agent_states_after"].items():
            for argument_id, belief in viewpoint_state["belief_states"].items():
                subagent = self.subagents[argument_id]
                if viewpoint_id != self.primary_owner[argument_id]:
                    continue
                subagent.belief_status = belief["agent_belief_status"]
                subagent.confidence = belief["confidence"]
                subagent.active = belief["activity"] == "active"

    def observe_and_revise(
        self,
        argument_id: str,
        messages: list[Any],
        timestamp: str,
        step: int,
        core_config: Any,
    ) -> list[dict[str, Any]]:
        """Reuse core observed-action weights over delivered messages only."""
        agent = self.subagents[argument_id]
        revisions: list[dict[str, Any]] = []
        for message in messages:
            old_confidence = agent.confidence
            old_status = agent.belief_status
            if message.message_type == "SUPPORT":
                delta = core_config.reasoning.observed_support_action
            elif message.message_type in {"PROVIDE_EVIDENCE", "ARGUMENT_AVAILABLE"}:
                delta = (
                    core_config.reasoning.observed_evidence_action
                    if message.message_type == "PROVIDE_EVIDENCE" else 0.0
                )
            elif message.message_type == "ATTACK":
                delta = -core_config.reasoning.observed_attack_action
            elif message.message_type == "CHALLENGE":
                delta = -core_config.reasoning.observed_challenge_action
            elif message.message_type == "RETRACTION":
                delta = -old_confidence
            else:
                delta = 0.0
            new_confidence = rounded(max(0.0, min(1.0, old_confidence + delta)))
            if message.message_type == "RETRACTION":
                new_status = "retracted"
            elif new_confidence >= core_config.accepted_threshold:
                new_status = "accepted"
            elif new_confidence <= core_config.rejected_threshold:
                new_status = "rejected"
            else:
                new_status = "undecided"
            revision = {
                "revision_id": f"HIER-REV-{message.message_id}",
                "argument_agent_id": agent.agent_id,
                "argument_id": argument_id,
                "timestamp": timestamp,
                "deliberation_step": step,
                "message_id": message.message_id,
                "message_type": message.message_type,
                "old_status": old_status,
                "new_status": new_status,
                "old_confidence": old_confidence,
                "new_confidence": new_confidence,
                "rule": "core observed-action weight, gated by hierarchy delivery",
            }
            agent.confidence = new_confidence
            agent.belief_status = new_status
            agent.revision_history.append(revision)
            revisions.append(revision)
        return revisions

    def aggregate(
        self,
        step: dict[str, Any],
        relations: list[dict[str, Any]],
    ) -> dict[str, ViewpointMacroAgent]:
        cohesion_rows = step["viewpoint_dynamics"]["cohesion_by_agent"]
        result: dict[str, ViewpointMacroAgent] = {}
        for row in self.mapping["viewpoints"]:
            argument_ids = row["argument_ids"]
            agents = [self.subagents[argument_id] for argument_id in argument_ids]
            visible = [agent for agent in agents if argument_id_visible(agent, step["timestamp"])]
            statuses = [agent.belief_status for agent in visible]
            confidences = [agent.confidence for agent in visible]
            internal = [
                relation for relation in relations
                if relation["source"] in argument_ids and relation["target"] in argument_ids
            ]
            disagreement = min(1.0, pstdev(confidences) / 0.5) if len(confidences) > 1 else 0.0
            center = mean(confidences) if confidences else 0.0
            contributors = sorted(
                (
                    {
                        "argument_id": agent.argument_id,
                        "confidence": agent.confidence,
                        "distance_from_viewpoint_mean": rounded(abs(agent.confidence - center)),
                        "belief_status": agent.belief_status,
                    }
                    for agent in visible
                ),
                key=lambda item: (-item["distance_from_viewpoint_mean"], item["argument_id"]),
            )
            cohesion = cohesion_rows.get(row["viewpoint_id"], {}).get("cohesion", 0.0)
            result[row["viewpoint_id"]] = ViewpointMacroAgent(
                agent_id=row["viewpoint_id"],
                kind=row["kind"],
                name=row["name"],
                argument_agent_ids=[agent.agent_id for agent in agents],
                accepted_count=statuses.count("accepted"),
                rejected_count=statuses.count("rejected"),
                undecided_count=statuses.count("undecided"),
                retracted_count=statuses.count("retracted"),
                active_argument_count=sum(agent.active for agent in visible),
                mean_confidence=rounded(mean(confidences) if confidences else 0.0),
                internal_support=sum(item["relation_type"] == "support" for item in internal),
                internal_attack=sum(item["relation_type"] == "attack" for item in internal),
                disagreement=rounded(disagreement),
                cohesion=cohesion,
                split_contributors=contributors[:3],
            )
        return result

    def trace_mapping(self) -> dict[str, list[str]]:
        return {
            row["viewpoint_id"]: [argument_agent_id(item) for item in row["argument_ids"]]
            for row in self.mapping["viewpoints"]
        }


def argument_id_visible(agent: ArgumentSubAgent, timestamp: str) -> bool:
    return int(agent.introduced_at[1:]) <= int(timestamp[1:])
