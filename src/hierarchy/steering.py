from __future__ import annotations

from typing import Any

from core.models import rounded
from society.config import SteeringConfig
from society.steering import SteeringEvaluator

from .config import PropagationConfig


class ArrivalAwareSteeringEvaluator(SteeringEvaluator):
    """Society linkage/semantic evidence with arrival-aware temporal precedence."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        trace: dict[str, Any],
        config: SteeringConfig,
        propagation: PropagationConfig,
    ) -> None:
        super().__init__(data, snapshots, trace, config)
        self.propagation = propagation
        self.steps_by_snapshot = {
            run["timestamp"]: max(1, len(run["steps"]))
            for run in trace["timestamps"]
        }
        self.snapshot_offsets: dict[str, int] = {}
        offset = 0
        for run in trace["timestamps"]:
            timestamp = run["timestamp"]
            self.snapshot_offsets[timestamp] = offset
            offset += self.steps_by_snapshot[timestamp]

    def pairwise(self, source_id: str, target_id: str, start_index: int, end_index: int) -> dict[str, Any]:
        row = super().pairwise(source_id, target_id, start_index, end_index)
        source_snapshot = self.selected[source_id]["introduced_at"]
        target_snapshot = self.selected[target_id]["introduced_at"]
        source_rank = self.rank[source_snapshot]
        target_rank = self.rank[target_snapshot]
        publication_precedence = 1.0 if source_rank < target_rank else 0.0
        delay = self.propagation.delay_for("ARGUMENT_AVAILABLE")
        publish_ordinal = self.snapshot_offsets[source_snapshot]
        arrival_ordinal = publish_ordinal + delay
        formation_ordinal = self.snapshot_offsets[target_snapshot]
        crossed_snapshot = arrival_ordinal >= (
            publish_ordinal + self.steps_by_snapshot[source_snapshot]
        )
        arrival_precedence = 1.0 if arrival_ordinal < formation_ordinal else 0.0
        influence = rounded(arrival_precedence * row["L"] * row["P"])
        row.update({
            "T": arrival_precedence,
            "T_delta": arrival_precedence,
            "I": influence,
            "publication_precedence": publication_precedence,
            "arrival_precedence": arrival_precedence,
            "source_publish_snapshot": source_snapshot,
            "target_formation_snapshot": target_snapshot,
            "assumed_delay": delay,
            "delay_mode": self.propagation.mode,
            "delay_evidence": "Cấu hình sensitivity theo k; không phải độ trễ thực địa đã đo.",
            "real_world_exposure": "unknown",
            "arrival_model": {
                "publish_ordinal": publish_ordinal,
                "arrival_ordinal": arrival_ordinal,
                "target_formation_ordinal": formation_ordinal,
                "source_snapshot_steps": self.steps_by_snapshot[source_snapshot],
                "crossed_snapshot_boundary": crossed_snapshot,
                "calendar_timestamp_created": False,
            },
            "explanation": (
                f"Theo cấu hình {self.propagation.mode}, thông tin về {source_id} "
                f"{'có thể đến trước' if arrival_precedence else 'không đến trước'} lúc {target_id} hình thành; "
                f"I={arrival_precedence:.1f}×{row['L']:.4f}×{row['P']:.4f}={influence:.4f}. "
                "Tiếp xúc ngoài đời thực: chưa biết."
            ),
        })
        if influence == 0.0:
            row["evidence_level"] = "NONE"
        return row
