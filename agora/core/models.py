from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    PRESENT_ARGUMENT = "PRESENT_ARGUMENT"
    SUPPORT = "SUPPORT"
    ATTACK = "ATTACK"
    CHALLENGE = "CHALLENGE"
    PROVIDE_EVIDENCE = "PROVIDE_EVIDENCE"
    RETRACT = "RETRACT"
    NO_OP = "NO_OP"


class BeliefStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNDECIDED = "undecided"
    RETRACTED = "retracted"


@dataclass
class BeliefState:
    argument_id: str
    canonical_status: str
    agent_belief_status: str
    confidence: float
    activity: str
    support_set: list[str]
    attack_set: list[str]
    evidence_sources: list[str]
    provenance: dict[str, Any]
    last_updated_at: str
    last_updated_step: int
    revision_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentObservation:
    observation_id: str
    agent_id: str
    timestamp: str
    deliberation_step: int
    newly_introduced_arguments: list[str]
    newly_introduced_evidence: list[str]
    incoming_support: list[dict[str, Any]]
    incoming_attacks: list[dict[str, Any]]
    other_agent_actions: list[dict[str, Any]]
    canonical_status_changes: list[dict[str, Any]]
    source_status_changes: list[dict[str, Any]]
    current_temporal_context: dict[str, Any]
    relevant_relations: list[dict[str, Any]]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReasoningTrace:
    agent_id: str
    argument_id: str
    timestamp: str
    deliberation_step: int
    canonical_status: str
    agent_belief_status_before: str
    score_before: float
    score_after: float
    recommended_status: str
    supporting_factors: list[dict[str, Any]]
    attacking_factors: list[dict[str, Any]]
    source_factors: list[dict[str, Any]]
    relation_ids: list[str]
    source_ids: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentAction:
    action_id: str
    timestamp: str
    deliberation_step: int
    actor_agent: str
    target_agent: str | None
    action_type: str
    source_argument_id: str | None
    target_argument_id: str | None
    relation_ids: list[str]
    evidence_source_ids: list[str]
    rationale: str
    utility: float
    provenance: dict[str, Any]
    valid: bool = False
    validation_reason: str = "not_validated"

    def signature(self) -> tuple:
        return (
            self.actor_agent, self.target_agent, self.action_type,
            self.source_argument_id, self.target_argument_id, tuple(self.relation_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InteractionRecord:
    interaction_id: str
    timestamp: str
    deliberation_step: int
    action_id: str
    actor_agent: str
    target_agent: str | None
    action_type: str
    source_argument_id: str | None
    target_argument_id: str | None
    relation_ids: list[str]
    evidence_source_ids: list[str]
    delivered: bool
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BeliefRevision:
    revision_id: str
    agent_id: str
    argument_id: str
    timestamp: str
    deliberation_step: int
    old_status: str
    new_status: str
    old_confidence: float
    new_confidence: float
    canonical_status: str
    trigger_action_ids: list[str]
    observation_id: str
    reasoning_trace_argument_id: str
    relation_ids: list[str]
    evidence_source_ids: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def rounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)
