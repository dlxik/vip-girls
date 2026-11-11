from __future__ import annotations

from typing import Any

from .agent import ArgumentativeAgent
from .config import SimulationConfig
from .models import AgentObservation, ReasoningTrace, rounded


class ReasoningEngine:
    def evaluate(
        self, agent: ArgumentativeAgent, observation: AgentObservation, snapshot: dict[str, Any]
    ) -> list[ReasoningTrace]:
        raise NotImplementedError


class WeightedArgumentReasoner(ReasoningEngine):
    """Transparent heuristic scorer; it is not a validated argumentation semantics."""

    def __init__(self, config: SimulationConfig, sources: list[dict[str, str]]) -> None:
        self.config = config
        self.sources = {row["source_id"]: row for row in sources}

    def _status_for_score(self, score: float) -> str:
        if score >= self.config.accepted_threshold:
            return "accepted"
        if score <= self.config.rejected_threshold:
            return "rejected"
        return "undecided"

    def evaluate(
        self, agent: ArgumentativeAgent, observation: AgentObservation, snapshot: dict[str, Any]
    ) -> list[ReasoningTrace]:
        relation_by_id = {row["id"]: row for row in snapshot["relations"]}
        traces: list[ReasoningTrace] = []
        for argument_id, belief in sorted(agent.belief_base.items()):
            support_factors: list[dict[str, Any]] = []
            attack_factors: list[dict[str, Any]] = []
            source_factors: list[dict[str, Any]] = []
            base = self.config.reasoning.canonical_status[belief.canonical_status]
            support_factors.append({
                "factor": "canonical_status_baseline", "value": base,
                "basis": belief.canonical_status,
            })
            score = base
            relation_ids: list[str] = []
            for relation_id in belief.support_set:
                relation = relation_by_id.get(relation_id)
                if not relation:
                    continue
                multiplier = self.config.reasoning.relation_confidence[relation["confidence"]]
                value = self.config.reasoning.incoming_support * multiplier
                score += value
                relation_ids.append(relation_id)
                support_factors.append({"factor": "incoming_support", "value": rounded(value), "relation_id": relation_id})
            for relation_id in belief.attack_set:
                relation = relation_by_id.get(relation_id)
                if not relation:
                    continue
                multiplier = self.config.reasoning.relation_confidence[relation["confidence"]]
                value = self.config.reasoning.incoming_attack * multiplier
                score -= value
                relation_ids.append(relation_id)
                attack_factors.append({"factor": "incoming_attack", "value": rounded(-value), "relation_id": relation_id})
            qualities = []
            for source_id in belief.evidence_sources:
                source = self.sources[source_id]
                authority = self.config.reasoning.source_authority[source["source_type"]]
                verification = self.config.reasoning.verification_quality.get(source["verification_status"], 0.4)
                quality = authority * verification
                qualities.append(quality)
                source_factors.append({
                    "source_id": source_id,
                    "source_type": source["source_type"],
                    "verification_status": source["verification_status"],
                    "quality": rounded(quality),
                })
            if qualities:
                evidence_value = self.config.reasoning.evidence_quality * (sum(qualities) / len(qualities) - 0.5)
                score += evidence_value
                support_factors.append({"factor": "evidence_quality_centered", "value": rounded(evidence_value)})
            if belief.activity == "historical":
                score -= self.config.reasoning.historical_penalty
                attack_factors.append({"factor": "historical_activity", "value": -self.config.reasoning.historical_penalty})
            for action in observation.other_agent_actions:
                if action.get("target_argument_id") != argument_id:
                    continue
                action_type = action["action_type"]
                if action_type == "SUPPORT":
                    value = self.config.reasoning.observed_support_action
                elif action_type == "PROVIDE_EVIDENCE":
                    value = self.config.reasoning.observed_evidence_action
                elif action_type == "ATTACK":
                    value = -self.config.reasoning.observed_attack_action
                elif action_type == "CHALLENGE":
                    value = -self.config.reasoning.observed_challenge_action
                else:
                    value = 0.0
                score += value
                bucket = support_factors if value >= 0 else attack_factors
                bucket.append({"factor": f"observed_{action_type.lower()}", "value": value, "action_id": action["action_id"]})
            score = rounded(score)
            recommended = self._status_for_score(score)
            traces.append(ReasoningTrace(
                agent_id=agent.agent_id,
                argument_id=argument_id,
                timestamp=observation.timestamp,
                deliberation_step=observation.deliberation_step,
                canonical_status=belief.canonical_status,
                agent_belief_status_before=belief.agent_belief_status,
                score_before=rounded(belief.confidence),
                score_after=score,
                recommended_status=recommended,
                supporting_factors=support_factors,
                attacking_factors=attack_factors,
                source_factors=source_factors,
                relation_ids=sorted(set(relation_ids)),
                source_ids=sorted(belief.evidence_sources),
                reason=(
                    f"Điểm nội bộ {score:.4f} từ canonical status, relation có confidence, "
                    "chất lượng nguồn, activity và action đã quan sát; không thay đổi canonical status."
                ),
            ))
        return traces
