from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bluesky.v2.models import rounded

from .config_v3 import SemanticsConfig


class ArgumentationSemantics(ABC):
    @abstractmethod
    def evaluate(
        self,
        argument_scores: dict[str, float],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError


class WeightedBipolarSemantics(ArgumentationSemantics):
    """Deterministic fixed-point baseline over the canonical bipolar graph.

    For an argument with relations, relational_signal is the weighted mean of
    supporter scores minus attacker scores, in [-1, 1]. The update is:

      s' = (1-d) * base + d * (0.5 + 0.5 * relational_signal)

    Arguments without incoming relations retain their base heuristic score.
    This is an explainable baseline, not ASPIC+ and not a truth estimator.
    """

    def __init__(
        self,
        config: SemanticsConfig,
        relation_confidence: dict[str, float],
        use_relation_confidence: bool = True,
    ) -> None:
        self.config = config
        self.relation_confidence = relation_confidence
        self.use_relation_confidence = use_relation_confidence

    def _status(self, score: float) -> str:
        if score >= self.config.accepted_threshold:
            return "accepted"
        if score <= self.config.rejected_threshold:
            return "rejected"
        return "undecided"

    def evaluate(
        self,
        argument_scores: dict[str, float],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        argument_ids = sorted(argument_scores)
        visible = set(argument_ids)
        usable = [
            relation for relation in relations
            if relation["source"] in visible and relation["target"] in visible
        ]
        incoming: dict[str, list[dict[str, Any]]] = {argument_id: [] for argument_id in argument_ids}
        for relation in usable:
            incoming[relation["target"]].append(relation)
        scores = {key: rounded(value) for key, value in argument_scores.items()}
        iteration_trace: list[dict[str, Any]] = []
        converged = False
        for iteration in range(self.config.max_iterations):
            updated: dict[str, float] = {}
            max_delta = 0.0
            for argument_id in argument_ids:
                relations_in = incoming[argument_id]
                if not relations_in:
                    updated[argument_id] = rounded(argument_scores[argument_id])
                    continue
                support = 0.0
                attack = 0.0
                total_weight = 0.0
                for relation in relations_in:
                    weight = (
                        self.relation_confidence.get(relation["confidence"], 0.7)
                        if self.use_relation_confidence else 1.0
                    )
                    contribution = weight * scores[relation["source"]]
                    if relation["relation_type"] == "support":
                        support += contribution
                    else:
                        attack += contribution
                    total_weight += weight
                signal = (support - attack) / total_weight if total_weight else 0.0
                relational_target = 0.5 + 0.5 * signal
                value = (
                    (1.0 - self.config.damping) * argument_scores[argument_id]
                    + self.config.damping * relational_target
                )
                updated[argument_id] = rounded(value)
                max_delta = max(max_delta, abs(updated[argument_id] - scores[argument_id]))
            iteration_trace.append({"iteration": iteration, "max_delta": rounded(max_delta)})
            scores = updated
            if max_delta <= self.config.convergence_epsilon:
                converged = True
                break

        results: dict[str, dict[str, Any]] = {}
        for argument_id in argument_ids:
            contributions = []
            for relation in sorted(incoming[argument_id], key=lambda row: row["id"]):
                weight = (
                    self.relation_confidence.get(relation["confidence"], 0.7)
                    if self.use_relation_confidence else 1.0
                )
                signed = weight * scores[relation["source"]]
                if relation["relation_type"] == "attack":
                    signed *= -1
                contributions.append({
                    "relation_id": relation["id"],
                    "relation_type": relation["relation_type"],
                    "source_argument": relation["source"],
                    "source_score": scores[relation["source"]],
                    "relation_weight": rounded(weight),
                    "signed_contribution": rounded(signed),
                    "evidence_source_ids": list(relation["evidence_sources"]),
                })
            results[argument_id] = {
                "argument_id": argument_id,
                "heuristic_score": rounded(argument_scores[argument_id]),
                "semantic_score": scores[argument_id],
                "semantic_status": self._status(scores[argument_id]),
                "incoming_derivation": contributions,
                "explanation": (
                    "Weighted bipolar fixed-point: heuristic score được giữ làm base; "
                    "canonical support tăng và canonical attack giảm relational signal."
                ),
            }
        return {
            "method": "weighted_bipolar_fixed_point",
            "input_argument_ids": argument_ids,
            "input_relation_ids": sorted(row["id"] for row in usable),
            "weights": {
                "damping": self.config.damping,
                "relation_confidence": self.relation_confidence if self.use_relation_confidence else "ablated_uniform_1.0",
            },
            "thresholds": {
                "accepted": self.config.accepted_threshold,
                "rejected": self.config.rejected_threshold,
            },
            "converged": converged,
            "iterations": len(iteration_trace),
            "iteration_trace": iteration_trace,
            "results": results,
            "limitation": "Kết quả là acceptability proxy cấu trúc, không phải factual truth hoặc social consensus.",
        }
