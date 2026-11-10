from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ArgumentSubAgent:
    agent_id: str
    argument_id: str
    parent_viewpoint_id: str
    argument_type: str
    belief_status: str
    confidence: float
    active: bool
    introduced_at: str
    source_ids: list[str]
    evidence_ids: list[str] = field(default_factory=list)
    inbox: list[str] = field(default_factory=list)
    observed_message_ids: list[str] = field(default_factory=list)
    action_history: list[dict[str, Any]] = field(default_factory=list)
    revision_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ViewpointMacroAgent:
    agent_id: str
    kind: str
    name: str
    argument_agent_ids: list[str]
    accepted_count: int = 0
    rejected_count: int = 0
    undecided_count: int = 0
    retracted_count: int = 0
    active_argument_count: int = 0
    mean_confidence: float = 0.0
    internal_support: int = 0
    internal_attack: int = 0
    disagreement: float = 0.0
    cohesion: float = 0.0
    split_contributors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InformationMessage:
    message_id: str
    source_agent_id: str
    source_argument_id: str | None
    target_agent_id: str
    target_argument_id: str | None
    message_type: str
    sent_at_t: str
    sent_at_k: int
    delay_steps: int
    available_at_t: str
    available_at_k: int
    delivered_at_t: str | None = None
    delivered_at_k: int | None = None
    consumed_at_t: str | None = None
    consumed_at_k: int | None = None
    delivery_status: str = "queued"
    crossed_snapshot_boundary: bool = False
    relation_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
