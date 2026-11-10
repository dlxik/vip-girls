from __future__ import annotations

import hashlib
import json
from typing import Any

from .agent import ArgumentativeAgent, initialize_agents, sync_agents_to_snapshot
from .belief_revision import BeliefRevisionEngine
from .config import DEFAULT_CONFIG, SimulationConfig
from .explanation import concise_step_log
from .interaction import InteractionProtocol
from .metrics import SocietyMetrics
from .models import ActionType, InteractionRecord
from .observation import ObservationBuilder
from .policy import RuleBasedArgumentationPolicy
from .reasoning import WeightedArgumentReasoner


class AutonomousArgumentationSimulation:
    def __init__(self, data: dict[str, Any], snapshots: list[dict[str, Any]], config: SimulationConfig = DEFAULT_CONFIG) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config
        self.argument_owner = {
            argument_id: row["viewpoint_id"]
            for row in data["viewpoint_mapping"]["viewpoints"]
            for argument_id in row["argument_ids"]
        }
        self.source_ids = {row["source_id"] for row in data["sources"]}
        self.observer = ObservationBuilder(self.argument_owner)
        self.reasoner = WeightedArgumentReasoner(config, data["sources"])
        self.policy = RuleBasedArgumentationPolicy(config, self.argument_owner)
        self.reviser = BeliefRevisionEngine(config)
        self.metrics = SocietyMetrics()

    @staticmethod
    def _state_hash(agents: dict[str, ArgumentativeAgent]) -> str:
        payload = {
            agent_id: {
                argument_id: [belief.agent_belief_status, belief.confidence]
                for argument_id, belief in sorted(agent.belief_base.items())
            }
            for agent_id, agent in sorted(agents.items())
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def run(self, verbose: bool = False) -> dict[str, Any]:
        agents = initialize_agents(self.data["viewpoint_mapping"], self.snapshots[0], self.config)
        protocol = InteractionProtocol(agents, self.argument_owner, self.source_ids)
        timestamp_runs: list[dict[str, Any]] = []
        full_log: list[str] = []

        for timestamp_index, snapshot in enumerate(self.snapshots):
            timestamp = snapshot["timestamp"]["timestamp_id"]
            if timestamp_index:
                sync_agents_to_snapshot(agents, snapshot, self.data["viewpoint_mapping"], self.config)
            used_signatures: set[tuple] = set()
            prior_interactions: list[InteractionRecord] = []
            cumulative_interactions: list[InteractionRecord] = []
            seen_hashes = {self._state_hash(agents)}
            no_change_steps = 0
            steps: list[dict[str, Any]] = []
            stop_reason = "max_steps_reached"

            for k in range(self.config.max_deliberation_steps):
                observations = {
                    agent_id: self.observer.build(agent, snapshot, k, prior_interactions)
                    for agent_id, agent in sorted(agents.items())
                }
                reasoning = {
                    agent_id: self.reasoner.evaluate(agent, observations[agent_id], snapshot)
                    for agent_id, agent in sorted(agents.items())
                }
                candidate_actions = {
                    agent_id: self.policy.candidates(agent, observations[agent_id], reasoning[agent_id], snapshot)
                    for agent_id, agent in sorted(agents.items())
                }
                selected = {}
                for agent_id in sorted(agents):
                    action = self.policy.select(candidate_actions[agent_id], used_signatures)
                    protocol.validate(action, snapshot, used_signatures)
                    if not action.valid:
                        action = next(row for row in candidate_actions[agent_id] if row.action_type == ActionType.NO_OP.value)
                        protocol.validate(action, snapshot, used_signatures)
                    selected[agent_id] = action
                interactions = protocol.execute(list(selected.values()))
                for interaction in interactions:
                    used_signatures.add(selected[interaction.actor_agent].signature())
                cumulative_interactions.extend(interactions)
                revisions = self.reviser.apply(agents, observations, reasoning, interactions, timestamp, k)
                for agent in agents.values():
                    agent.state_history.append({"timestamp": timestamp, "step": k, "state": agent.snapshot_state()})

                all_no_op = all(row.action_type == ActionType.NO_OP.value for row in selected.values())
                state_hash = self._state_hash(agents)
                repeated_state = state_hash in seen_hashes
                no_change_steps = no_change_steps + 1 if not revisions else 0
                no_change_stop = no_change_steps >= self.config.no_change_patience and repeated_state
                will_stop = all_no_op or no_change_stop
                metrics = self.metrics.compute(agents, interactions, revisions, cumulative_interactions, converged=will_stop)
                step_record = {
                    "timestamp": timestamp,
                    "deliberation_step": k,
                    "observations": {key: value.to_dict() for key, value in observations.items()},
                    "reasoning_traces": {key: [row.to_dict() for row in value] for key, value in reasoning.items()},
                    "candidate_actions": {key: [row.to_dict() for row in value] for key, value in candidate_actions.items()},
                    "selected_actions": {key: value.to_dict() for key, value in selected.items()},
                    "interactions": [row.to_dict() for row in interactions],
                    "belief_revisions": [row.to_dict() for row in revisions],
                    "society_metrics": metrics,
                    "agent_states_after": {key: value.snapshot_state() for key, value in sorted(agents.items())},
                    "state_hash": state_hash,
                }
                step_record["log"] = concise_step_log(step_record)
                steps.append(step_record)
                full_log.extend(step_record["log"])
                if all_no_op:
                    stop_reason = "all_agents_no_op"
                    break
                if no_change_stop:
                    stop_reason = "no_belief_change_and_repeated_state"
                    break
                seen_hashes.add(state_hash)
                prior_interactions = interactions

            if steps and stop_reason == "max_steps_reached":
                steps[-1]["society_metrics"]["convergence_indicator"] = False
            timestamp_runs.append({
                "timestamp": timestamp,
                "temporal_context": snapshot["timestamp"],
                "steps": steps,
                "stop_reason": stop_reason,
                "steps_executed": len(steps),
                "final_agent_states": {key: value.snapshot_state() for key, value in sorted(agents.items())},
            })

        result = {
            "schema_version": "agora-v2-trace-1.0",
            "model": "autonomous argumentative agents with deterministic symbolic reasoning and explicit belief revision",
            "time_semantics": {
                "t": "real CTQ information snapshot",
                "k": "internal deliberation step inside one real timestamp",
            },
            "config": self.config.to_dict(),
            "argument_owner": dict(sorted(self.argument_owner.items())),
            "argument_catalog": {
                argument["id"]: {
                    "id": argument["id"],
                    "arg_type": argument["arg_type"],
                    "premise": argument["premise"],
                    "rule": argument["rule"],
                    "conclusion": argument["conclusion"],
                    "source_ids": argument["source_ids"],
                    "source_type": argument["source_type"],
                    "sources": argument["sources"],
                    "introduced_at": argument["introduced_at"],
                    "active_until": argument["active_until"],
                    "temporal_role": argument["temporal_role"],
                }
                for argument in self.snapshots[-1]["arguments"]
            },
            "timestamps": timestamp_runs,
            "deterministic_log": full_log,
            "limitations": [
                "Heuristic weights are explicit experimental defaults, not theoretically validated strengths.",
                "Viewpoint mapping is manual and mutually exclusive.",
                "No factual claim, source, or support/attack relation is generated by the simulation.",
            ],
        }
        if verbose:
            print("\n".join(full_log))
        return result
