from __future__ import annotations

from dataclasses import asdict, dataclass, field

from bluesky.v3.config_v3 import DEFAULT_V3_CONFIG, V3Config


VALID_PROPAGATION_MODES = {"zero_delay", "fixed_delay", "action_type_delay"}


@dataclass(frozen=True)
class PropagationConfig:
    """Logical-k propagation assumptions, not measured real-world latency."""

    enabled: bool = True
    mode: str = "zero_delay"
    default_delay_steps: int = 0
    carry_across_snapshots: bool = True
    action_type_delays: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in VALID_PROPAGATION_MODES:
            raise ValueError(f"Propagation mode không hợp lệ: {self.mode}")
        if self.default_delay_steps < 0:
            raise ValueError("default_delay_steps phải >= 0")
        if any(value < 0 for value in self.action_type_delays.values()):
            raise ValueError("action_type_delays phải >= 0")
        if self.mode == "zero_delay" and self.default_delay_steps != 0:
            raise ValueError("zero_delay yêu cầu default_delay_steps = 0")

    def delay_for(self, message_type: str) -> int:
        if not self.enabled or self.mode == "zero_delay":
            return 0
        if self.mode == "action_type_delay":
            return self.action_type_delays.get(message_type, self.default_delay_steps)
        return self.default_delay_steps


@dataclass(frozen=True)
class V4Config:
    v3: V3Config = field(default_factory=lambda: DEFAULT_V3_CONFIG)
    propagation: PropagationConfig = field(default_factory=PropagationConfig)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_V4_CONFIG = V4Config()
