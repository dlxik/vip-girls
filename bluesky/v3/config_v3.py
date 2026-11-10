from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from bluesky.v2.config import DEFAULT_CONFIG, ReasoningWeights, SimulationConfig


@dataclass(frozen=True)
class SemanticsConfig:
    damping: float = 0.35
    convergence_epsilon: float = 0.0001
    max_iterations: int = 40
    accepted_threshold: float = 0.62
    rejected_threshold: float = 0.38


@dataclass(frozen=True)
class ViewpointDynamicsConfig:
    split_candidate_threshold: float = 0.45
    merge_candidate_threshold: float = 0.68
    stabilization_threshold: float = 0.72
    persistent_steps: int = 2
    enable_runtime_split_merge: bool = False


@dataclass(frozen=True)
class DynamicsConfig:
    persistent_conflict_steps: int = 2
    confidence_gap_threshold: float = 0.08
    consensus_threshold: float = 0.72
    fragmentation_threshold: float = 0.25


@dataclass(frozen=True)
class ConflictConfig:
    relation_confidence: dict[str, float] = field(default_factory=lambda: {
        "high": 1.0, "medium": 0.7,
    })
    authority_weights: dict[str, float] = field(default_factory=lambda: {
        "official_document": 1.0,
        "authority_statement": 0.85,
        "news": 0.55,
        "social": 0.35,
    })
    verification_weights: dict[str, float] = field(default_factory=lambda: {
        "verified": 1.0,
        "verified_copy": 0.9,
        "partially_verified": 0.65,
        "needs_human_review": 0.4,
    })
    status_validity: dict[str, float] = field(default_factory=lambda: {
        "accepted": 1.0, "undecided": 0.6, "rejected": 0.25,
    })
    historical_multiplier: float = 0.35


@dataclass(frozen=True)
class SteeringConfig:
    linkage_weights: dict[str, float] = field(default_factory=lambda: {
        "direct_relation": 0.45,
        "reverse_response_relation": 0.20,
        "interaction_reaches_target_owner": 0.20,
        "linked_belief_revision": 0.15,
    })
    canonical_relation_semantic_floor: float = 0.85
    semantic_method: str = "canonical_relation_else_conclusion_token_jaccard"
    medium_evidence_threshold: float = 0.20
    strong_evidence_threshold: float = 0.75


@dataclass(frozen=True)
class RiskConfig:
    alpha: float = 0.5
    beta: float = 0.2
    gamma: float = 0.3
    low_threshold: float = 0.30
    medium_threshold: float = 0.50
    high_threshold: float = 0.70
    risk_alert_threshold: float = 0.70
    high_conflict_threshold: float = 0.70
    high_steering_threshold: float = 0.25
    risk_increase_threshold: float = 0.10
    conflict_increase_threshold: float = 0.10
    steering_persistence_windows: int = 2
    assessment_medium_threshold: float = 0.35
    assessment_high_threshold: float = 0.75


@dataclass(frozen=True)
class AblationConfig:
    source_quality: bool = True
    relation_confidence: bool = True
    observed_action_effects: bool = True
    institutional_policy: bool = True
    viewpoint_dynamics: bool = True


@dataclass(frozen=True)
class V3Config:
    v2: SimulationConfig = field(default_factory=lambda: DEFAULT_CONFIG)
    semantics: SemanticsConfig = field(default_factory=SemanticsConfig)
    semantic_revision_blend: float = 0.35
    viewpoint_dynamics: ViewpointDynamicsConfig = field(default_factory=ViewpointDynamicsConfig)
    dynamics: DynamicsConfig = field(default_factory=DynamicsConfig)
    conflict: ConflictConfig = field(default_factory=ConflictConfig)
    steering: SteeringConfig = field(default_factory=SteeringConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ablations: AblationConfig = field(default_factory=AblationConfig)

    def effective_v2_config(self) -> SimulationConfig:
        reasoning: ReasoningWeights = self.v2.reasoning
        if not self.ablations.source_quality:
            reasoning = replace(reasoning, evidence_quality=0.0)
        if not self.ablations.relation_confidence:
            reasoning = replace(
                reasoning,
                relation_confidence={key: 1.0 for key in reasoning.relation_confidence},
            )
        if not self.ablations.observed_action_effects:
            reasoning = replace(
                reasoning,
                observed_support_action=0.0,
                observed_attack_action=0.0,
                observed_challenge_action=0.0,
                observed_evidence_action=0.0,
            )
        return replace(self.v2, reasoning=reasoning)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_V3_CONFIG = V3Config()
