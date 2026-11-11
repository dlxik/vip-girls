from __future__ import annotations

from typing import Any

from .config import DEFAULT_HIERARCHY_CONFIG, HierarchyConfig, PropagationConfig
from .simulation import HierarchicalArgumentSocietySimulation


class PropagationEvaluationRunner:
    def __init__(self, data: dict[str, Any], snapshots: list[dict[str, Any]]) -> None:
        self.data = data
        self.snapshots = snapshots

    @staticmethod
    def _summary(trace: dict[str, Any]) -> dict[str, Any]:
        full = trace["risk_monitoring"]["by_window"]["t1__t6"]
        steps = [step for run in trace["timestamps"] for step in run["steps"]]
        return {
            "propagation": trace["propagation_assumption"],
            "interactions": sum(len(step["interactions"]) for step in steps),
            "viewpoint_belief_revisions": sum(len(step["belief_revisions"]) for step in steps),
            "argument_agent_revisions": sum(len(step["argument_agent_revisions"]) for step in steps),
            "messages": len(trace["message_trace"]),
            "delivered_messages": sum(
                message["delivered_at_t"] is not None for message in trace["message_trace"]
            ),
            "steering_scores": {
                row["argument_id"]: row["steering_score"] for row in full["ranked_arguments"]
            },
            "risk_ranking": [row["argument_id"] for row in full["ranked_arguments"]],
            "risk_scores": {
                row["argument_id"]: row["risk_score"] for row in full["ranked_arguments"]
            },
            "dominant_viewpoint": trace["timestamps"][-1]["steps"][-1][
                "society_metrics"
            ]["dominant_viewpoint"],
            "society_events": len(trace["society_events"]),
            "split_candidates": sum(
                len(step["viewpoint_dynamics"]["split_candidates"]) for step in steps
            ),
            "merge_candidates": sum(
                len(step["viewpoint_dynamics"]["merge_candidates"]) for step in steps
            ),
        }

    def run(self) -> dict[str, Any]:
        zero = HierarchicalArgumentSocietySimulation(
            self.data, self.snapshots, DEFAULT_HIERARCHY_CONFIG
        ).run()
        fixed_config = HierarchyConfig(
            society=DEFAULT_HIERARCHY_CONFIG.society,
            propagation=PropagationConfig(mode="fixed_delay", default_delay_steps=1),
        )
        fixed = HierarchicalArgumentSocietySimulation(
            self.data, self.snapshots, fixed_config
        ).run()
        zero_summary = self._summary(zero)
        fixed_summary = self._summary(fixed)
        return {
            "model": "Propagation sensitivity; not empirical delay estimation",
            "scenario_zero_delay": zero_summary,
            "scenario_fixed_delay_1k": fixed_summary,
            "comparison": {
                "steering_changed_arguments": sorted(
                    argument_id for argument_id, score in zero_summary["steering_scores"].items()
                    if fixed_summary["steering_scores"].get(argument_id) != score
                ),
                "risk_ranking_changed": (
                    zero_summary["risk_ranking"] != fixed_summary["risk_ranking"]
                ),
                "dominant_viewpoint_changed": (
                    zero_summary["dominant_viewpoint"] != fixed_summary["dominant_viewpoint"]
                ),
                "interpretation": (
                    "Hierarchy layer nới giả định thông tin đồng bộ và cho phép phân tích độ nhạy dưới độ trễ; "
                    "không chứng minh độ trễ thực địa."
                ),
            },
        }
