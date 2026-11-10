from __future__ import annotations

from typing import Any

from bluesky.v2.models import rounded

from .config_v3 import RiskConfig
from .explanation_v3 import alert_explanation, risk_explanation


class RiskEvaluator:
    """Configurable baseline operationalization of RS=f(C,S)."""

    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def band(self, score: float) -> str:
        if score < self.config.low_threshold:
            return "LOW"
        if score < self.config.medium_threshold:
            return "MEDIUM"
        if score < self.config.high_threshold:
            return "MEDIUM_HIGH"
        return "HIGH"

    def assessment_quality(self, conflict: dict[str, Any], steering: dict[str, Any]) -> dict[str, Any]:
        conflict_quality = 1.0 if conflict["maximizing_pair"] else 0.0
        level_value = {"NONE": 0.0, "WEAK": 0.4, "MEDIUM": 0.75, "STRONG": 1.0}
        steering_quality = max(
            (level_value[row["evidence_level"]] for row in steering["pairwise_influence"]),
            default=0.0,
        )
        score = rounded((conflict_quality + steering_quality) / 2.0)
        if score >= self.config.assessment_high_threshold:
            category = "HIGH"
        elif score >= self.config.assessment_medium_threshold:
            category = "MEDIUM"
        else:
            category = "LOW"
        return {
            "category": category,
            "score": score,
            "conflict_evidence_quality": conflict_quality,
            "steering_evidence_quality": steering_quality,
            "rule": "trung bình(bằng chứng xung đột có căn cứ, mức bằng chứng định hướng theo cặp mạnh nhất)",
            "note": "Chất lượng đánh giá được hiển thị riêng và không được nhân vào RS.",
        }

    def evaluate(self, argument_id: str, conflict: dict[str, Any], steering: dict[str, Any]) -> dict[str, Any]:
        c = conflict["conflict_score"]
        s = steering["steering_score"]
        c_contribution = rounded(self.config.alpha * c)
        s_contribution = rounded(self.config.beta * s)
        interaction_contribution = rounded(self.config.gamma * c * s)
        score = rounded(c_contribution + s_contribution + interaction_contribution)
        return {
            "argument_id": argument_id,
            "risk_score": score,
            "risk_band": self.band(score),
            "above_risk_threshold": score >= self.config.risk_alert_threshold,
            "contributions": {
                "conflict": c_contribution,
                "steering": s_contribution,
                "interaction_cs": interaction_contribution,
            },
            "coefficients": {
                "alpha": self.config.alpha,
                "beta": self.config.beta,
                "gamma": self.config.gamma,
            },
            "assessment_quality": self.assessment_quality(conflict, steering),
            "formula": "RS(x,H)=alpha*C(x,H)+beta*S(x,H)+gamma*C(x,H)*S(x,H)",
            "explanation": risk_explanation(argument_id, c, s, score),
            "limitation": "Cách vận hành cơ sở của f(C,S); có thể cấu hình và chưa được hiệu chỉnh thực nghiệm.",
        }

    def alerts(
        self,
        argument_id: str,
        current: dict[str, float],
        previous: dict[str, float] | None,
        steering_streak: int,
    ) -> list[dict[str, Any]]:
        alerts = []
        previous_risk = previous["risk"] if previous else None
        previous_conflict = previous["conflict"] if previous else None
        if current["risk"] >= self.config.risk_alert_threshold and (
            previous_risk is None or previous_risk < self.config.risk_alert_threshold
        ):
            alerts.append({
                "type": "HIGH_RISK", "argument_id": argument_id,
                "reason": alert_explanation("HIGH_RISK", current["risk"], previous_risk, self.config.risk_alert_threshold),
            })
        if previous_risk is not None and current["risk"] - previous_risk >= self.config.risk_increase_threshold:
            alerts.append({
                "type": "RISK_INCREASE", "argument_id": argument_id,
                "reason": alert_explanation("RISK_INCREASE", current["risk"], previous_risk, self.config.risk_increase_threshold),
            })
        if previous_conflict is not None and current["conflict"] - previous_conflict >= self.config.conflict_increase_threshold:
            alerts.append({
                "type": "CONFLICT_INCREASE", "argument_id": argument_id,
                "reason": alert_explanation("CONFLICT_INCREASE", current["conflict"], previous_conflict, self.config.conflict_increase_threshold),
            })
        if steering_streak >= self.config.steering_persistence_windows:
            alerts.append({
                "type": "STEERING_PERSISTS", "argument_id": argument_id,
                "reason": alert_explanation(
                    "STEERING_PERSISTS", current["steering"],
                    previous["steering"] if previous else None,
                    self.config.high_steering_threshold,
                ),
            })
        return alerts
