from __future__ import annotations

from typing import Any

from .agent import ArgumentativeAgent
from .config import SimulationConfig
from .models import AgentObservation, BeliefRevision, InteractionRecord, ReasoningTrace, rounded


class BeliefRevisionEngine:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def _status(self, confidence: float, old_status: str) -> str:
        if old_status == "retracted":
            return "retracted"
        if confidence >= self.config.accepted_threshold:
            return "accepted"
        if confidence <= self.config.rejected_threshold:
            return "rejected"
        return "undecided"

    def apply(
        self,
        agents: dict[str, ArgumentativeAgent],
        observations: dict[str, AgentObservation],
        reasoning: dict[str, list[ReasoningTrace]],
        interactions: list[InteractionRecord],
        timestamp: str,
        deliberation_step: int,
    ) -> list[BeliefRevision]:
        revisions: list[BeliefRevision] = []
        interactions_by_target: dict[tuple[str, str], list[InteractionRecord]] = {}
        for interaction in interactions:
            if interaction.action_type == "RETRACT" and interaction.source_argument_id:
                interactions_by_target.setdefault((interaction.actor_agent, interaction.source_argument_id), []).append(interaction)
            elif interaction.target_agent and interaction.target_argument_id:
                interactions_by_target.setdefault((interaction.target_agent, interaction.target_argument_id), []).append(interaction)

        revision_index = 0
        for agent_id, traces in sorted(reasoning.items()):
            agent = agents[agent_id]
            for trace in traces:
                belief = agent.belief_base[trace.argument_id]
                old_confidence = belief.confidence
                old_status = belief.agent_belief_status
                blended = old_confidence + self.config.reasoning_blend * (trace.score_after - old_confidence)
                triggers = interactions_by_target.get((agent_id, trace.argument_id), [])
                delta = 0.0
                for item in triggers:
                    if item.action_type == "SUPPORT":
                        delta += self.config.reasoning.observed_support_action
                    elif item.action_type == "PROVIDE_EVIDENCE":
                        delta += self.config.reasoning.observed_evidence_action
                    elif item.action_type == "ATTACK":
                        delta -= self.config.reasoning.observed_attack_action
                    elif item.action_type == "CHALLENGE":
                        delta -= self.config.reasoning.observed_challenge_action
                    elif item.action_type == "RETRACT":
                        blended = min(blended, self.config.retract_threshold)
                new_confidence = rounded(blended + delta)
                new_status = "retracted" if any(row.action_type == "RETRACT" for row in triggers) else self._status(new_confidence, old_status)
                if abs(new_confidence - old_confidence) < self.config.confidence_change_epsilon and new_status == old_status:
                    continue
                revision_index += 1
                relation_ids = sorted({rid for row in triggers for rid in row.relation_ids} | set(trace.relation_ids))
                source_ids = sorted({sid for row in triggers for sid in row.evidence_source_ids} | set(trace.source_ids))
                trigger_ids = [row.action_id for row in triggers]
                explanation = (
                    f"Belief nội bộ cập nhật từ {old_confidence:.4f} thành {new_confidence:.4f}: "
                    f"blend với symbolic score {trace.score_after:.4f}"
                    + (f" và action {', '.join(trigger_ids)}" if trigger_ids else "")
                    + "; canonical status được giữ nguyên."
                )
                belief.confidence = new_confidence
                belief.agent_belief_status = new_status
                belief.last_updated_at = timestamp
                belief.last_updated_step = deliberation_step
                belief.revision_reason = explanation
                revisions.append(BeliefRevision(
                    revision_id=f"REV-{timestamp}-k{deliberation_step}-{revision_index:03d}",
                    agent_id=agent_id,
                    argument_id=trace.argument_id,
                    timestamp=timestamp,
                    deliberation_step=deliberation_step,
                    old_status=old_status,
                    new_status=new_status,
                    old_confidence=rounded(old_confidence),
                    new_confidence=new_confidence,
                    canonical_status=belief.canonical_status,
                    trigger_action_ids=trigger_ids,
                    observation_id=observations[agent_id].observation_id,
                    reasoning_trace_argument_id=trace.argument_id,
                    relation_ids=relation_ids,
                    evidence_source_ids=source_ids,
                    explanation=explanation,
                ))
        return revisions
