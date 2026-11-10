from __future__ import annotations

from dataclasses import replace
from typing import Any

from .config_v3 import AblationConfig, V3Config
from .simulation_v3 import DynamicSocietySimulation


def _signature(trace: dict[str, Any]) -> dict[str, Any]:
    last = trace["timestamps"][-1]["steps"][-1]
    final_beliefs = {
        agent_id: {
            argument_id: [belief["agent_belief_status"], belief["confidence"]]
            for argument_id, belief in state["belief_states"].items()
        }
        for agent_id, state in last["agent_states_after"].items()
    }
    return {
        "final_beliefs": final_beliefs,
        "dominant_viewpoint": last["society_metrics_v3"]["dominant_viewpoint"],
        "split_candidates": last["society_metrics_v3"]["split_candidates"],
        "merge_candidates": last["society_metrics_v3"]["merge_candidates"],
        "simulation_convergence": last["society_metrics_v3"]["simulation_convergence"],
        "convergence_proxy": last["society_metrics_v3"]["convergence_proxy"],
        "event_types": sorted(event["event_type"] for event in trace["society_events"]),
    }


class EvaluationRunner:
    def __init__(self, data: dict[str, Any], snapshots: list[dict[str, Any]]) -> None:
        self.data = data
        self.snapshots = snapshots

    def run(self, baseline: V3Config) -> dict[str, Any]:
        sensitivity = {
            "reasoning_support_weight_high": replace(
                baseline,
                v2=replace(
                    baseline.v2,
                    reasoning=replace(baseline.v2.reasoning, incoming_support=0.16),
                ),
            ),
            "semantics_damping_low": replace(
                baseline, semantics=replace(baseline.semantics, damping=0.20)
            ),
            "semantics_damping_high": replace(
                baseline, semantics=replace(baseline.semantics, damping=0.55)
            ),
            "strict_thresholds": replace(
                baseline,
                semantics=replace(baseline.semantics, accepted_threshold=0.70, rejected_threshold=0.30),
            ),
            "semantic_revision_blend_low": replace(baseline, semantic_revision_blend=0.15),
            "semantic_revision_blend_high": replace(baseline, semantic_revision_blend=0.60),
            "max_steps_3": replace(baseline, v2=replace(baseline.v2, max_deliberation_steps=3)),
        }
        ablations = {
            "without_source_quality": replace(baseline, ablations=replace(baseline.ablations, source_quality=False)),
            "without_relation_confidence": replace(baseline, ablations=replace(baseline.ablations, relation_confidence=False)),
            "without_action_effects": replace(baseline, ablations=replace(baseline.ablations, observed_action_effects=False)),
            "without_institutional_policy": replace(baseline, ablations=replace(baseline.ablations, institutional_policy=False)),
            "without_viewpoint_dynamics": replace(baseline, ablations=replace(baseline.ablations, viewpoint_dynamics=False)),
        }
        baseline_trace = DynamicSocietySimulation(self.data, self.snapshots, baseline).run()
        return {
            "baseline": _signature(baseline_trace),
            "sensitivity": {
                name: {"config": config.to_dict(), "outcome": _signature(DynamicSocietySimulation(self.data, self.snapshots, config).run())}
                for name, config in sensitivity.items()
            },
            "ablation": {
                name: {"config": config.to_dict(), "outcome": _signature(DynamicSocietySimulation(self.data, self.snapshots, config).run())}
                for name, config in ablations.items()
            },
            "interpretation": "Differences are simulation sensitivity/ablation results, not empirical causal effects.",
        }
