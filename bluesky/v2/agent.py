from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .config import SimulationConfig
from .models import BeliefState


@dataclass
class ArgumentativeAgent:
    agent_id: str
    kind: str
    name: str
    position_summary: str
    belief_base: dict[str, BeliefState] = field(default_factory=dict)
    evidence_base: set[str] = field(default_factory=set)
    active_arguments: set[str] = field(default_factory=set)
    historical_arguments: set[str] = field(default_factory=set)
    observations: list[dict[str, Any]] = field(default_factory=list)
    interaction_history: list[dict[str, Any]] = field(default_factory=list)
    action_history: list[dict[str, Any]] = field(default_factory=list)
    state_history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def belief_states(self) -> dict[str, BeliefState]:
        """Explicit alias used by the V2 conceptual model and serialized UI state."""
        return self.belief_base

    def snapshot_state(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind,
            "name": self.name,
            "position_summary": self.position_summary,
            "active_arguments": sorted(self.active_arguments),
            "historical_arguments": sorted(self.historical_arguments),
            "evidence_base": sorted(self.evidence_base),
            "belief_states": {
                key: value.to_dict() for key, value in sorted(self.belief_base.items())
            },
        }

    def clone_state(self) -> dict[str, BeliefState]:
        return deepcopy(self.belief_base)


def _initial_confidence(canonical_status: str, config: SimulationConfig) -> float:
    return config.reasoning.canonical_status[canonical_status]


def initialize_agents(
    mapping: dict[str, Any], snapshot: dict[str, Any], config: SimulationConfig
) -> dict[str, ArgumentativeAgent]:
    agents = {
        row["viewpoint_id"]: ArgumentativeAgent(
            agent_id=row["viewpoint_id"],
            kind=row["kind"],
            name=row["name"],
            position_summary=row["position_summary"],
        )
        for row in mapping["viewpoints"]
    }
    sync_agents_to_snapshot(agents, snapshot, mapping, config, deliberation_step=0)
    return agents


def sync_agents_to_snapshot(
    agents: dict[str, ArgumentativeAgent],
    snapshot: dict[str, Any],
    mapping: dict[str, Any],
    config: SimulationConfig,
    deliberation_step: int = 0,
) -> None:
    owner = {
        argument_id: row["viewpoint_id"]
        for row in mapping["viewpoints"]
        for argument_id in row["argument_ids"]
    }
    timestamp = snapshot["timestamp"]["timestamp_id"]
    for argument in snapshot["arguments"]:
        agent = agents[owner[argument["id"]]]
        belief = agent.belief_base.get(argument["id"])
        if belief is None:
            belief = BeliefState(
                argument_id=argument["id"],
                canonical_status=argument["semantic_status"],
                agent_belief_status=argument["semantic_status"],
                confidence=_initial_confidence(argument["semantic_status"], config),
                activity=argument["activity"],
                support_set=list(argument["incoming_support"]),
                attack_set=list(argument["incoming_attack"]),
                evidence_sources=list(argument["source_ids"]),
                provenance={
                    "argument_id": argument["id"],
                    "source_ids": list(argument["source_ids"]),
                    "status_grounded_by": list(argument["grounded_by"]),
                },
                last_updated_at=timestamp,
                last_updated_step=deliberation_step,
                revision_reason="Khởi tạo từ canonical status; confidence là trạng thái mô phỏng nội bộ.",
            )
            agent.belief_base[argument["id"]] = belief
        else:
            belief.canonical_status = argument["semantic_status"]
            belief.activity = argument["activity"]
            belief.support_set = list(argument["incoming_support"])
            belief.attack_set = list(argument["incoming_attack"])
            belief.evidence_sources = list(argument["source_ids"])
            belief.provenance["status_grounded_by"] = list(argument["grounded_by"])
        agent.evidence_base.update(argument["source_ids"])
        if argument["activity"] == "active":
            agent.active_arguments.add(argument["id"])
            agent.historical_arguments.discard(argument["id"])
        else:
            agent.historical_arguments.add(argument["id"])
            agent.active_arguments.discard(argument["id"])
    for agent in agents.values():
        agent.state_history.append({"timestamp": timestamp, "step": deliberation_step, "state": agent.snapshot_state()})
