from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class InstitutionalActionType(str, Enum):
    PROVIDE_EVIDENCE = "PROVIDE_EVIDENCE"
    CLARIFY_NORM = "CLARIFY_NORM"
    CLARIFY_AUTHORITY = "CLARIFY_AUTHORITY"
    CHALLENGE_INVALID_GROUNDING = "CHALLENGE_INVALID_GROUNDING"
    NO_OP = "NO_OP"


class SocietyEventType(str, Enum):
    DOMINANCE_SHIFT = "DOMINANCE_SHIFT"
    VIEWPOINT_SPLIT_CANDIDATE = "VIEWPOINT_SPLIT_CANDIDATE"
    VIEWPOINT_MERGE_CANDIDATE = "VIEWPOINT_MERGE_CANDIDATE"
    VIEWPOINT_SPLIT = "VIEWPOINT_SPLIT"
    VIEWPOINT_MERGE = "VIEWPOINT_MERGE"
    CONVERGENCE_PROXY = "CONVERGENCE_PROXY"
    FRAGMENTATION_PROXY = "FRAGMENTATION_PROXY"
    PERSISTENT_CONFLICT = "PERSISTENT_CONFLICT"
    STABILIZATION = "STABILIZATION"


@dataclass
class SocietyEvent:
    event_id: str
    timestamp: str
    deliberation_step: int
    event_type: str
    involved_agents: list[str]
    involved_arguments: list[str]
    metric_snapshot: dict[str, Any]
    threshold: dict[str, Any]
    explanation: str
    provenance: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeViewpoint:
    runtime_id: str
    kind: str
    parent_viewpoints: list[str]
    argument_ids: list[str]
    created_at: str
    created_step: int
    trigger_event_id: str | None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DominanceRecord:
    timestamp: str
    deliberation_step: int
    dominant_agent: str | None
    structural_prevalence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
