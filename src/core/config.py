from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ReasoningWeights:
    canonical_status: dict[str, float] = field(default_factory=lambda: {
        "accepted": 0.68, "undecided": 0.50, "rejected": 0.30,
    })
    relation_confidence: dict[str, float] = field(default_factory=lambda: {
        "high": 1.0, "medium": 0.7,
    })
    incoming_support: float = 0.10
    incoming_attack: float = 0.12
    evidence_quality: float = 0.10
    source_authority: dict[str, float] = field(default_factory=lambda: {
        "official_document": 1.0,
        "authority_statement": 0.85,
        "news": 0.55,
        "social": 0.35,
    })
    verification_quality: dict[str, float] = field(default_factory=lambda: {
        "verified": 1.0,
        "verified_copy": 0.9,
        "partially_verified": 0.65,
        "needs_human_review": 0.4,
    })
    historical_penalty: float = 0.08
    observed_support_action: float = 0.06
    observed_attack_action: float = 0.08
    observed_challenge_action: float = 0.05
    observed_evidence_action: float = 0.07


@dataclass(frozen=True)
class PolicyWeights:
    action_base: dict[str, float] = field(default_factory=lambda: {
        "PRESENT_ARGUMENT": 0.40,
        "SUPPORT": 0.62,
        "ATTACK": 0.72,
        "CHALLENGE": 0.56,
        "PROVIDE_EVIDENCE": 0.60,
        "RETRACT": 0.78,
        "NO_OP": 0.0,
    })
    high_relation_bonus: float = 0.08
    medium_relation_bonus: float = 0.04
    new_argument_bonus: float = 0.05
    evidence_bonus: float = 0.04
    historical_penalty: float = 0.08


@dataclass(frozen=True)
class SimulationConfig:
    reasoning: ReasoningWeights = field(default_factory=ReasoningWeights)
    policy: PolicyWeights = field(default_factory=PolicyWeights)
    max_deliberation_steps: int = 5
    accepted_threshold: float = 0.62
    rejected_threshold: float = 0.38
    retract_threshold: float = 0.22
    reasoning_blend: float = 0.35
    confidence_change_epsilon: float = 0.0001
    no_change_patience: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = SimulationConfig()
