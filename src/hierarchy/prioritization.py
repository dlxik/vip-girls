from __future__ import annotations

from typing import Any

from society.prioritization import RiskMonitoringEngine

from .config import HierarchyConfig
from .steering import ArrivalAwareSteeringEvaluator


class ArrivalAwareRiskMonitoringEngine(RiskMonitoringEngine):
    """Inherit Society conflict/Risk/window logic; replace only Steering temporal T."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        trace: dict[str, Any],
        config: HierarchyConfig,
    ) -> None:
        super().__init__(data, snapshots, trace, config.society)
        self.hierarchy_config = config
        self.steering = ArrivalAwareSteeringEvaluator(
            data, snapshots, trace, config.society.steering, config.propagation
        )

    def build(self) -> dict[str, Any]:
        result = super().build()
        result["methodology"].update({
            "influence_formula": "I_arrival(A,B)=T_delta(A,B)*L(A,B)*P(A,B)",
            "arrival_condition": "T_delta=1 iff modeled arrival_B(A) < formation(B)",
            "propagation": {
                "mode": self.hierarchy_config.propagation.mode,
                "default_delay_steps": self.hierarchy_config.propagation.default_delay_steps,
                "unit": "logical deliberation step k",
                "real_world_exposure": "unknown",
            },
        })
        return result
