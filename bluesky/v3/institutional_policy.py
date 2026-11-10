from __future__ import annotations

from typing import Any

from bluesky.v2.agent import ArgumentativeAgent
from bluesky.v2.models import AgentAction, AgentObservation, ReasoningTrace, rounded

from .models import InstitutionalActionType


class InstitutionalActionPolicy:
    """Restricted, source-grounded policy for contextual/institutional agents."""

    allowed_actions = {item.value for item in InstitutionalActionType}
    forbidden_direct_controls = {
        "FORCE_BELIEF", "SET_CONFIDENCE", "SUPPRESS_AGENT", "FORCE_CONVERGENCE",
        "ATTACK", "SUPPORT", "PRESENT_ARGUMENT", "RETRACT",
    }

    def __init__(
        self,
        argument_owner: dict[str, str],
        sources: list[dict[str, str]],
        argument_catalog: dict[str, Any],
    ) -> None:
        self.argument_owner = argument_owner
        self.source_by_id = {row["source_id"]: row for row in sources}
        self.argument_catalog = argument_catalog

    def _official(self, source_ids: list[str]) -> bool:
        return bool(source_ids) and all(
            self.source_by_id[source_id]["source_type"] in {"official_document", "authority_statement"}
            for source_id in source_ids
        )

    def _clarification_type(self, argument_id: str) -> str:
        argument = self.argument_catalog[argument_id]
        text = f"{argument.get('rule') or ''} {argument.get('conclusion') or ''}".lower()
        if any(term in text for term in ("thẩm quyền", "quyền", "ban chỉ đạo", "bộ trưởng")):
            return InstitutionalActionType.CLARIFY_AUTHORITY.value
        return InstitutionalActionType.CLARIFY_NORM.value

    def _action(
        self,
        agent: ArgumentativeAgent,
        observation: AgentObservation,
        index: int,
        action_type: str,
        source_argument: str | None,
        target_argument: str | None,
        relation: dict[str, Any] | None,
        evidence: list[str],
        rationale: str,
        utility: float,
    ) -> AgentAction:
        target_agent = self.argument_owner.get(target_argument or "")
        if target_agent == agent.agent_id:
            target_agent = None
        relation_ids = [relation["id"]] if relation else []
        return AgentAction(
            action_id=f"ACT-{observation.timestamp}-k{observation.deliberation_step}-{agent.agent_id}-{index:03d}",
            timestamp=observation.timestamp,
            deliberation_step=observation.deliberation_step,
            actor_agent=agent.agent_id,
            target_agent=target_agent,
            action_type=action_type,
            source_argument_id=source_argument,
            target_argument_id=target_argument,
            relation_ids=relation_ids,
            evidence_source_ids=sorted(set(evidence)),
            rationale=rationale,
            utility=rounded(utility),
            provenance={
                "argument_ids": sorted(set(filter(None, [source_argument, target_argument]))),
                "relation_ids": relation_ids,
                "source_ids": sorted(set(evidence)),
                "observation_id": observation.observation_id,
                "institutional_protocol": True,
            },
        )

    def candidates(
        self,
        agent: ArgumentativeAgent,
        observation: AgentObservation,
        reasoning: list[ReasoningTrace],
        snapshot: dict[str, Any],
    ) -> list[AgentAction]:
        del reasoning
        candidates: list[AgentAction] = []
        owned = set(agent.belief_base)
        index = 0
        for argument_id in observation.newly_introduced_arguments:
            evidence = agent.belief_base[argument_id].evidence_sources
            if not self._official(evidence):
                continue
            action_type = self._clarification_type(argument_id)
            index += 1
            candidates.append(self._action(
                agent, observation, index, action_type, argument_id, None, None, evidence,
                f"{action_type} từ argument thể chế {argument_id} và nguồn chính thức; không ép belief agent khác.",
                0.70,
            ))
        for relation in sorted(snapshot["relations"], key=lambda row: row["id"]):
            if relation["source"] not in owned:
                continue
            evidence = list(relation["evidence_sources"])
            if not self._official(evidence):
                continue
            if relation["relation_type"] == "support":
                action_type = self._clarification_type(relation["source"])
                utility = 0.68
            else:
                action_type = InstitutionalActionType.CHALLENGE_INVALID_GROUNDING.value
                utility = 0.66
            index += 1
            candidates.append(self._action(
                agent, observation, index, action_type,
                relation["source"], relation["target"], relation, evidence,
                f"{action_type} được ground bởi canonical relation {relation['id']} và nguồn chính thức.",
                utility + (0.06 if relation["confidence"] == "high" else 0.03),
            ))
            if relation["relation_type"] == "support" and evidence:
                index += 1
                candidates.append(self._action(
                    agent, observation, index, InstitutionalActionType.PROVIDE_EVIDENCE.value,
                    relation["source"], relation["target"], relation, evidence,
                    f"Cung cấp evidence chính thức của relation {relation['id']} qua interaction pipeline.",
                    0.67,
                ))
        index += 1
        candidates.append(self._action(
            agent, observation, index, InstitutionalActionType.NO_OP.value,
            None, None, None, [], "Không có clarification/evidence grounded phù hợp.", 0.0,
        ))
        return sorted(
            candidates,
            key=lambda row: (-row.utility, row.action_type, row.source_argument_id or "", row.target_argument_id or ""),
        )

    def select(self, candidates: list[AgentAction], used_signatures: set[tuple]) -> AgentAction:
        for candidate in candidates:
            if candidate.action_type != "NO_OP" and candidate.signature() not in used_signatures:
                return candidate
        return next(row for row in candidates if row.action_type == "NO_OP")

    def validate_restrictions(self, action: AgentAction) -> tuple[bool, str]:
        if action.action_type not in self.allowed_actions:
            return False, f"Institutional action {action.action_type} không thuộc allow-list."
        if action.action_type == "NO_OP":
            return True, "NO_OP hợp lệ."
        if not self._official(action.evidence_source_ids):
            return False, "Institutional influence phải ground bằng official/documentary source."
        if action.action_type in self.forbidden_direct_controls:
            return False, "Institutional agent không được trực tiếp điều khiển belief hoặc convergence."
        return True, "Institutional protocol hợp lệ; ảnh hưởng vẫn đi qua interaction và revision."
