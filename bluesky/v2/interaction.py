from __future__ import annotations

from typing import Any

from .agent import ArgumentativeAgent
from .models import ActionType, AgentAction, InteractionRecord


class InteractionProtocol:
    def __init__(
        self,
        agents: dict[str, ArgumentativeAgent],
        argument_owner: dict[str, str],
        canonical_source_ids: set[str],
    ) -> None:
        self.agents = agents
        self.argument_owner = argument_owner
        self.canonical_source_ids = canonical_source_ids

    def validate(self, action: AgentAction, snapshot: dict[str, Any], used_signatures: set[tuple]) -> AgentAction:
        if action.action_type == ActionType.NO_OP.value:
            action.valid, action.validation_reason = True, "NO_OP luôn hợp lệ."
            return action
        if action.signature() in used_signatures:
            action.valid, action.validation_reason = False, "Action trùng trong cùng timestamp."
            return action
        actor = self.agents.get(action.actor_agent)
        if actor is None or action.source_argument_id not in actor.belief_base:
            action.valid, action.validation_reason = False, "Actor không sở hữu source argument."
            return action
        if action.target_agent and action.target_agent not in self.agents:
            action.valid, action.validation_reason = False, "Target agent không tồn tại."
            return action
        if set(action.evidence_source_ids) - self.canonical_source_ids:
            action.valid, action.validation_reason = False, "Evidence source không thuộc canonical data."
            return action
        relation_by_id = {row["id"]: row for row in snapshot["relations"]}
        for relation_id in action.relation_ids:
            relation = relation_by_id.get(relation_id)
            if relation is None:
                action.valid, action.validation_reason = False, "Relation không tồn tại trong G_t."
                return action
            if not set(action.evidence_source_ids).issubset(set(relation["evidence_sources"])):
                action.valid, action.validation_reason = False, "Evidence không thuộc relation provenance."
                return action
            if action.action_type == ActionType.CHALLENGE.value:
                endpoints_ok = (
                    relation["relation_type"] == "attack"
                    and relation["target"] == action.source_argument_id
                    and relation["source"] == action.target_argument_id
                )
            else:
                endpoints_ok = (
                    relation["source"] == action.source_argument_id
                    and relation["target"] == action.target_argument_id
                )
            if not endpoints_ok:
                action.valid, action.validation_reason = False, "Action không khớp endpoints canonical relation."
                return action
        if action.action_type in {ActionType.SUPPORT.value, ActionType.ATTACK.value, ActionType.PROVIDE_EVIDENCE.value, ActionType.CHALLENGE.value} and not action.relation_ids:
            action.valid, action.validation_reason = False, "Action tương tác thiếu canonical relation."
            return action
        action.valid, action.validation_reason = True, "Grounding hợp lệ."
        return action

    def execute(self, actions: list[AgentAction]) -> list[InteractionRecord]:
        interactions: list[InteractionRecord] = []
        for index, action in enumerate(sorted(actions, key=lambda row: row.actor_agent), start=1):
            if not action.valid or action.action_type == ActionType.NO_OP.value:
                continue
            record = InteractionRecord(
                interaction_id=f"INT-{action.timestamp}-k{action.deliberation_step}-{index:03d}",
                timestamp=action.timestamp,
                deliberation_step=action.deliberation_step,
                action_id=action.action_id,
                actor_agent=action.actor_agent,
                target_agent=action.target_agent,
                action_type=action.action_type,
                source_argument_id=action.source_argument_id,
                target_argument_id=action.target_argument_id,
                relation_ids=list(action.relation_ids),
                evidence_source_ids=list(action.evidence_source_ids),
                delivered=action.target_agent is not None,
                provenance=dict(action.provenance),
            )
            interactions.append(record)
            self.agents[action.actor_agent].action_history.append(action.to_dict())
            self.agents[action.actor_agent].interaction_history.append(record.to_dict())
            if action.target_agent:
                self.agents[action.target_agent].interaction_history.append(record.to_dict())
        return interactions
