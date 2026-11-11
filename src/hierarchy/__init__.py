"""Hierarchical argument agents and deterministic propagation."""

from .config import DEFAULT_HIERARCHY_CONFIG, HierarchyConfig, PropagationConfig
from .simulation import HierarchicalArgumentSocietySimulation

__all__ = [
    "DEFAULT_HIERARCHY_CONFIG",
    "PropagationConfig",
    "HierarchyConfig",
    "HierarchicalArgumentSocietySimulation",
]
