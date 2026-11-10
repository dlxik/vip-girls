from __future__ import annotations

from typing import Any

from .config_v3 import V3Config
from .conflict import ConflictEvaluator
from .explanation_v3 import priority_explanation
from .risk import RiskEvaluator
from .steering import SteeringEvaluator


class RiskMonitoringEngine:
    """Build deterministic rankings for every valid snapshot-bounded window H."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        trace: dict[str, Any],
        config: V3Config,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.trace = trace
        self.config = config
        self.conflict = ConflictEvaluator(data, snapshots, config.conflict)
        self.steering = SteeringEvaluator(data, snapshots, trace, config.steering)
        self.risk = RiskEvaluator(config.risk)
        self.catalog = trace["argument_catalog"]

    def _validate_window(self, start_index: int, end_index: int) -> None:
        size = len(self.data["timeline"])
        if not 0 <= start_index < size or not 0 <= end_index < size:
            raise ValueError(f"Chỉ số snapshot ngoài phạm vi: {start_index}..{end_index}")
        if start_index > end_index:
            raise ValueError(
                f"Cửa sổ snapshot không hợp lệ: start={start_index} > end={end_index}"
            )

    def _window_id(self, start_index: int, end_index: int) -> str:
        start = self.data["timeline"][start_index]["timestamp_id"]
        end = self.data["timeline"][end_index]["timestamp_id"]
        return f"{start}__{end}"

    def build_window(self, start_index: int, end_index: int) -> dict[str, Any]:
        """Compute one analytical window from its actual snapshot boundaries."""
        self._validate_window(start_index, end_index)
        start = self.data["timeline"][start_index]
        end = self.data["timeline"][end_index]
        eligible = self.steering.eligible_discourse(start_index, end_index)
        rows = []
        for argument_id in eligible:
            conflict = self.conflict.evaluate(argument_id, start_index, end_index)
            steering = self.steering.evaluate(argument_id, start_index, end_index)
            risk = self.risk.evaluate(argument_id, conflict, steering)
            row = {
                "argument_id": argument_id,
                "conclusion": self.catalog[argument_id]["conclusion"],
                "owner_viewpoint": self.trace["argument_owner"][argument_id],
                "introduced_at": self.catalog[argument_id]["introduced_at"],
                "conflict_score": conflict["conflict_score"],
                "steering_score": steering["steering_score"],
                "risk_score": risk["risk_score"],
                "risk_band": risk["risk_band"],
                "assessment_quality": risk["assessment_quality"],
                "above_risk_threshold": risk["above_risk_threshold"],
                "above_conflict_threshold": (
                    conflict["conflict_score"] >= self.config.risk.high_conflict_threshold
                ),
                "above_steering_threshold": (
                    steering["steering_score"] >= self.config.risk.high_steering_threshold
                ),
                "conflict_evidence": conflict,
                "steering_evidence": steering,
                "risk_detail": risk,
                "alerts": [],
                "trend": {
                    "basis": "analytical_window",
                    "conflict_delta": None,
                    "steering_delta": None,
                    "risk_delta": None,
                },
            }
            rows.append(row)
        ranked = sorted(rows, key=lambda row: (-row["risk_score"], row["argument_id"]))
        for rank, row in enumerate(ranked, 1):
            row["priority_rank"] = rank
            row["priority_explanation"] = priority_explanation(
                row["argument_id"], rank, row["risk_score"]
            )
        return {
            "window_id": self._window_id(start_index, end_index),
            "start_snapshot": start["timestamp_id"],
            "end_snapshot": end["timestamp_id"],
            "start_index": start_index,
            "end_index": end_index,
            "H_l": start["date_start"],
            "H_u": end["date_end"],
            "start_label": start["label"],
            "end_label": end["label"],
            "is_cumulative": start_index == 0,
            "monitored_argument_count": len(ranked),
            "high_risk_count": sum(row["above_risk_threshold"] for row in ranked),
            "high_conflict_count": sum(row["above_conflict_threshold"] for row in ranked),
            "high_steering_count": sum(row["above_steering_threshold"] for row in ranked),
            "risk_set_X_R": [row["argument_id"] for row in ranked if row["above_risk_threshold"]],
            "ranked_arguments": ranked,
        }

    def build(self) -> dict[str, Any]:
        timeline = self.data["timeline"]
        by_window = {
            self._window_id(start_index, end_index): self.build_window(start_index, end_index)
            for start_index in range(len(timeline))
            for end_index in range(start_index, len(timeline))
        }
        history: dict[str, list[dict[str, Any]]] = {
            argument_id: []
            for argument_id, row in self.catalog.items() if row["arg_type"] == "A_D"
        }
        previous: dict[str, dict[str, float]] = {}
        steering_streaks = {argument_id: 0 for argument_id in history}
        all_alerts = []
        cumulative_windows: dict[str, str] = {}
        for end_index, endpoint in enumerate(timeline):
            window_id = self._window_id(0, end_index)
            cumulative_windows[endpoint["timestamp_id"]] = window_id
            window = by_window[window_id]
            for row in window["ranked_arguments"]:
                argument_id = row["argument_id"]
                current = {
                    "conflict": row["conflict_score"],
                    "steering": row["steering_score"],
                    "risk": row["risk_score"],
                }
                steering_streaks[argument_id] = (
                    steering_streaks[argument_id] + 1
                    if current["steering"] >= self.config.risk.high_steering_threshold else 0
                )
                alerts = self.risk.alerts(
                    argument_id, current, previous.get(argument_id), steering_streaks[argument_id]
                )
                prior = previous.get(argument_id, current)
                row["alerts"] = alerts
                row["trend"] = {
                    "basis": "cumulative_H_t",
                    "conflict_delta": round(current["conflict"] - prior["conflict"], 4),
                    "steering_delta": round(current["steering"] - prior["steering"], 4),
                    "risk_delta": round(current["risk"] - prior["risk"], 4),
                }
                previous[argument_id] = current
                all_alerts.extend({"window_id": window_id, **alert} for alert in alerts)
                history[row["argument_id"]].append({
                    "window_id": window_id,
                    "start_snapshot": timeline[0]["timestamp_id"],
                    "end_snapshot": endpoint["timestamp_id"],
                    "H_l": timeline[0]["date_start"],
                    "H_u": endpoint["date_end"],
                    "conflict": row["conflict_score"],
                    "steering": row["steering_score"],
                    "risk": row["risk_score"],
                    "risk_band": row["risk_band"],
                    "assessment_quality": row["assessment_quality"]["category"],
                    "rank": row["priority_rank"],
                })
        return {
            "methodology": {
                "scope": "Rank_H(B) chỉ áp dụng trên B(H), là tập con của A_D",
                "window_semantics": "H=[t_start,t_end] trên các mốc snapshot t1...t6; không phải quan sát liên tục từng ngày.",
                "conflict_formula": "C(x,H)=max_{k in A_K(H)} Attack*RelationConfidence*Validity*Authority",
                "influence_formula": "I(A,B)=T(A,B)*L(A,B)*P(A,B)",
                "steering_formula": "S(x,H)=sum_{j!=i} I(x,x_j)/max(1,|A_D(H)|-1)",
                "risk_formula": "RS(x,H)=alpha*C(x,H)+beta*S(x,H)+gamma*C(x,H)*S(x,H)",
                "config": {
                    "conflict": self.config.to_dict()["conflict"],
                    "steering": self.config.to_dict()["steering"],
                    "risk": self.config.to_dict()["risk"],
                },
                "thresholds": {
                    "LOW": f"< {self.config.risk.low_threshold}",
                    "MEDIUM": f"[{self.config.risk.low_threshold}, {self.config.risk.medium_threshold})",
                    "MEDIUM_HIGH": f"[{self.config.risk.medium_threshold}, {self.config.risk.high_threshold})",
                    "HIGH": f">= {self.config.risk.high_threshold}",
                    "tau_C": self.config.risk.high_conflict_threshold,
                    "tau_S": self.config.risk.high_steering_threshold,
                    "tau_R": self.config.risk.risk_alert_threshold,
                },
                "limitations": [
                    "Xung đột chỉ tính quan hệ tấn công có hướng chính tắc và tường minh; không tự tạo mâu thuẫn từ văn bản.",
                    "Định hướng là chỉ báo bằng chứng liên kết, không phải ảnh hưởng hay tiếp xúc nhân quả đã được chứng minh.",
                    "Rủi ro là đường cơ sở có thể cấu hình để ưu tiên rà soát, không phải mức độ gây hại thực tế.",
                    "k chỉ được dùng làm bằng chứng mô phỏng; H bị chặn bởi các snapshot quan sát, không phải chuỗi ngày liên tục.",
                ],
            },
            "snapshot_options": [
                {
                    "snapshot_id": row["timestamp_id"],
                    "index": index,
                    "label": row["label"],
                    "date_start": row["date_start"],
                    "date_end": row["date_end"],
                }
                for index, row in enumerate(timeline)
            ],
            "window_order": list(by_window),
            "cumulative_windows": cumulative_windows,
            "by_window": by_window,
            "argument_history": history,
            "alerts": all_alerts,
        }
