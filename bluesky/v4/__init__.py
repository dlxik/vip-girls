"""AGORA V4: hierarchical argument agents and deterministic propagation."""

from .config_v4 import DEFAULT_V4_CONFIG, PropagationConfig, V4Config
from .simulation_v4 import HierarchicalArgumentSocietySimulation

__all__ = [
    "DEFAULT_V4_CONFIG",
    "PropagationConfig",
    "V4Config",
    "HierarchicalArgumentSocietySimulation",
]
