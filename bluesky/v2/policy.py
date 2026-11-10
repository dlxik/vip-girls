from __future__ import annotations

from typing import Any

from .agent import ArgumentativeAgent
from .config import SimulationConfig
from .models import ActionType, AgentAction, AgentObservation, ReasoningTrace, rounded


class ActionPolicy:
    def candidates(
        self,
        agent: ArgumentativeAgent,
        observation: AgentObservation,
        reasoning: list[ReasoningTrace],
        snapshot: dict[str, Any],
    ) -> list[AgentAction]:
        raise NotImplementedError

    def select(self, candidates: list[AgentAction], used_signatures: set[tuple]) -> AgentAction:
        raise NotImplementedError


class RuleBasedArgumentationPolicy(ActionPolicy):
    def __init__(self, config: SimulationConfig, argument_owner: dict[str, str]) -> None:
        self.config = config
        self.argument_owner = argument_owner

    def _utility(self, action_type: str, relation: dict[str, Any] | None, historical: bool, evidence: bool) -> float:
        value = self.config.policy.action_base[action_type]
        if relation:
            value += self.config.policy.high_relation_bonus if relation["confidence"] == "high" else self.config.policy.medium_relation_bonus
        if evidence:
            value += self.config.policy.evidence_bonus
        if historical:
            value -= self.config.policy.historical_penalty
        return rounded(value)

    def _action(
        self, agent: ArgumentativeAgent, observation: AgentObservation, index: int,
        action_type: str, source_argument_id: str | None, target_argument_id: str | None,
        relation: dict[str, Any] | None, evidence: list[str], rationale: str,
    ) -> AgentAction:
        target_agent = self.argument_owner.get(target_argument_id or "")
        if target_agent == agent.agent_id:
            target_agent = None
        relation_ids = [relation["id"]] if relation else []
        historical = bool(source_argument_id and source_argument_id in agent.historical_arguments)
        return AgentAction(
            action_id=f"ACT-{observation.timestamp}-k{observation.deliberation_step}-{agent.agent_id}-{index:03d}",
            timestamp=observation.timestamp,
            deliberation_step=observation.deliberation_step,
            actor_agent=agent.agent_id,
            target_agent=target_agent,
            action_type=action_type,
            source_argument_id=source_argument_id,
            target_argument_id=target_argument_id,
            relation_ids=relation_ids,
            evidence_source_ids=sorted(set(evidence)),
            rationale=rationale,
            utility=self._utility(action_type, relation, historical, bool(evidence)),
            provenance={
                "argument_ids": sorted(set(filter(None, [source_argument_id, target_argument_id]))),
                "relation_ids": relation_ids,
                "source_ids": sorted(set(evidence)),
                "observation_id": observation.observation_id,
            },
        )

    def candidates(
        self,
        agent: ArgumentativeAgent,
        observation: AgentObservation,
        reasoning: list[ReasoningTrace],
        snapshot: dict[str, Any],
    ) -> list[AgentAction]:
        candidates: list[AgentAction] = []
        trace_by_id = {row.argument_id: row for row in reasoning}
        relations = sorted(snapshot["relations"], key=lambda row: row["id"])
        owned = set(agent.belief_base)
        index = 0

        for argument_id in observation.newly_introduced_arguments:
            belief = agent.belief_base[argument_id]
            index += 1
            candidates.append(self._action(
                agent, observation, index, ActionType.PRESENT_ARGUMENT.value,
                argument_id, None, None, belief.evidence_sources,
                f"Trình bày argument mới {argument_id} đã xuất hiện trong G_{observation.timestamp}.",
            ))

        for relation in relations:
            source_id, target_id = relation["source"], relation["target"]
            if source_id in owned and self.argument_owner[target_id] != agent.agent_id:
                action_type = ActionType.SUPPORT.value if relation["relation_type"] == "support" else ActionType.ATTACK.value
                index += 1
                candidates.append(self._action(
                    agent, observation, index, action_type, source_id, target_id, relation,
                    relation["evidence_sources"],
                    f"{action_type} được phép bởi canonical relation {relation['id']} ({source_id} → {target_id}).",
                ))
                if relation["relation_type"] == "support" and relation["evidence_sources"]:
                    index += 1
                    candidates.append(self._action(
                        agent, observation, index, ActionType.PROVIDE_EVIDENCE.value,
                        source_id, target_id, relation, relation["evidence_sources"],
                        f"Cung cấp evidence của canonical support relation {relation['id']}.",
                    ))
            if target_id in owned and relation["relation_type"] == "attack" and self.argument_owner[source_id] != agent.agent_id:
                index += 1
                candidates.append(self._action(
                    agent, observation, index, ActionType.CHALLENGE.value,
                    target_id, source_id, relation, relation["evidence_sources"],
                    f"Thách thức incoming attack {relation['id']}; không tạo relation đảo chiều mới.",
                ))

        for argument_id, trace in sorted(trace_by_id.items()):
            belief = agent.belief_base[argument_id]
            if trace.score_after <= self.config.retract_threshold and belief.agent_belief_status != "retracted":
                index += 1
                candidates.append(self._action(
                    agent, observation, index, ActionType.RETRACT.value,
                    argument_id, None, None, belief.evidence_sources,
                    f"Điểm defensibility {trace.score_after:.4f} dưới ngưỡng retract {self.config.retract_threshold:.2f}.",
                ))

        index += 1
        candidates.append(self._action(
            agent, observation, index, ActionType.NO_OP.value,
            None, None, None, [], "Không thực hiện action nếu không còn lựa chọn grounded hợp lệ.",
        ))
        return sorted(candidates, key=lambda row: (-row.utility, row.action_type, row.source_argument_id or "", row.target_argument_id or ""))

    def select(self, candidates: list[AgentAction], used_signatures: set[tuple]) -> AgentAction:
        for candidate in candidates:
            if candidate.action_type != ActionType.NO_OP.value and candidate.signature() not in used_signatures:
                return candidate
        return next(row for row in candidates if row.action_type == ActionType.NO_OP.value)
