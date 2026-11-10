from __future__ import annotations

from typing import Any

from bluesky.v3.prioritization import RiskMonitoringEngine

from .config_v4 import V4Config
from .steering_v4 import ArrivalAwareSteeringEvaluator


class V4RiskMonitoringEngine(RiskMonitoringEngine):
    """Inherit V3 Conflict/Risk/window logic; replace only Steering temporal T."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        trace: dict[str, Any],
        config: V4Config,
    ) -> None:
        super().__init__(data, snapshots, trace, config.v3)
        self.v4_config = config
        self.steering = ArrivalAwareSteeringEvaluator(
            data, snapshots, trace, config.v3.steering, config.propagation
        )

    def build(self) -> dict[str, Any]:
        result = super().build()
        result["methodology"].update({
            "influence_formula": "I_V4(A,B)=T_delta(A,B)*L(A,B)*P(A,B)",
            "arrival_condition": "T_delta=1 iff modeled arrival_B(A) < formation(B)",
            "propagation": {
                "mode": self.v4_config.propagation.mode,
                "default_delay_steps": self.v4_config.propagation.default_delay_steps,
                "unit": "logical deliberation step k",
                "real_world_exposure": "unknown",
            },
        })
        return result
