from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

from core.agent import ArgumentativeAgent, initialize_agents, sync_agents_to_snapshot
from core.belief_revision import BeliefRevisionEngine
from core.interaction import InteractionProtocol
from core.metrics import SocietyMetrics
from core.models import ActionType, InteractionRecord, ReasoningTrace, rounded
from core.observation import ObservationBuilder
from core.policy import RuleBasedArgumentationPolicy
from core.reasoning import WeightedArgumentReasoner

from .config import DEFAULT_SOCIETY_CONFIG, SocietyConfig
from .explanation import society_step_log
from .institutional_policy import InstitutionalActionPolicy
from .metrics import DynamicSocietyMetrics
from .prevalence import StructuralPrevalenceCalculator
from .prioritization import RiskMonitoringEngine
from .semantics import WeightedBipolarSemantics
from .society_dynamics import SocietyDynamicsEngine
from .viewpoint_dynamics import RuntimeSocietyStructure, ViewpointDynamics


class DynamicSocietySimulation:
    """Dynamic-society orchestration reusing temporal snapshots and core agent engines."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        config: SocietyConfig = DEFAULT_SOCIETY_CONFIG,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config
        self.core_config = config.effective_core_config()
        self.base_mapping = deepcopy(data["viewpoint_mapping"])
        self.argument_owners: dict[str, list[str]] = {}
        for row in self.base_mapping["viewpoints"]:
            for argument_id in row["argument_ids"]:
                self.argument_owners.setdefault(argument_id, []).append(row["viewpoint_id"])
        self.argument_owner = {
            argument_id: owners[0] for argument_id, owners in self.argument_owners.items()
        }
        self.source_ids = {row["source_id"] for row in data["sources"]}
        self.argument_catalog = {
            argument["id"]: {
                key: argument[key]
                for key in (
                    "id", "arg_type", "premise", "rule", "conclusion", "source_ids",
                    "source_type", "sources", "introduced_at", "active_until", "temporal_role",
                )
            }
            for argument in snapshots[-1]["arguments"]
        }
        self.observer = ObservationBuilder(self.argument_owner)
        self.reasoner = WeightedArgumentReasoner(self.core_config, data["sources"])
        self.ordinary_policy = RuleBasedArgumentationPolicy(self.core_config, self.argument_owner)
        self.institutional_policy = InstitutionalActionPolicy(
            self.argument_owner, data["sources"], self.argument_catalog
        )
        self.reviser = BeliefRevisionEngine(self.core_config)
        self.core_metrics = SocietyMetrics()
        self.semantics = WeightedBipolarSemantics(
            config.semantics,
            self.core_config.reasoning.relation_confidence,
            use_relation_confidence=config.ablations.relation_confidence,
        )
        self.viewpoint_dynamics = ViewpointDynamics(config.viewpoint_dynamics, self.argument_catalog)
        self.prevalence = StructuralPrevalenceCalculator()
        self.dynamic_metrics = DynamicSocietyMetrics()
        self.dynamics = SocietyDynamicsEngine(config.dynamics, config.viewpoint_dynamics)
        self.runtime_structure = RuntimeSocietyStructure(self.base_mapping)
        self._structure_candidate_streaks: dict[tuple[str, ...], int] = {}

    @staticmethod
    def _split_groups(state: dict[str, Any]) -> list[list[str]]:
        by_status: dict[str, list[str]] = {}
        for argument_id, belief in state["belief_states"].items():
            by_status.setdefault(belief["agent_belief_status"], []).append(argument_id)
        groups = [sorted(group) for group in by_status.values() if group]
        if len(groups) >= 2:
            return sorted(groups, key=lambda group: (group[0], len(group)))
        ordered = sorted(
            state["belief_states"],
            key=lambda argument_id: (
                state["belief_states"][argument_id]["confidence"], argument_id
            ),
        )
        midpoint = len(ordered) // 2
        return [ordered[:midpoint], ordered[midpoint:]] if midpoint else []

    def _apply_runtime_structure_change(
        self,
        viewpoint_result: dict[str, Any],
        runtime_states: dict[str, dict[str, Any]],
        timestamp: str,
        step: int,
    ) -> list[dict[str, Any]]:
        if not (
            self.config.ablations.viewpoint_dynamics
            and self.config.viewpoint_dynamics.enable_runtime_split_merge
        ):
            return []
        current_keys: set[tuple[str, ...]] = set()
        candidates: list[tuple[float, tuple[str, ...], dict[str, Any]]] = []
        for candidate in viewpoint_result["split_candidates"]:
            key = ("split", candidate["agent_id"], *candidate["argument_ids"])
            current_keys.add(key)
            candidates.append((candidate["score"], key, candidate))
        for candidate in viewpoint_result["merge_candidates"]:
            key = ("merge", *candidate["agents"])
            current_keys.add(key)
            candidates.append((candidate["score"], key, candidate))
        self._structure_candidate_streaks = {
            key: self._structure_candidate_streaks.get(key, 0) + 1
            for key in current_keys
        }
        persistent = self.config.viewpoint_dynamics.persistent_steps
        eligible = [
            item for item in candidates
            if self._structure_candidate_streaks.get(item[1], 0) >= persistent
        ]
        if not eligible:
            return []
        score, key, candidate = sorted(eligible, key=lambda item: (-item[0], item[1]))[0]
        trigger = f"STRUCT-{timestamp}-k{step}"
        if key[0] == "split":
            parent = candidate["agent_id"]
            groups = self._split_groups(runtime_states[parent])
            if len(groups) < 2 or any(not group for group in groups):
                return []
            created = self.runtime_structure.register_split(
                parent, groups, timestamp, step, trigger
            )
            change = {
                "operation": "split",
                "retired_viewpoints": [parent],
                "created_viewpoints": created,
                "argument_groups": groups,
                "score": score,
                "persistent_steps": persistent,
            }
        else:
            parents = candidate["agents"]
            created = self.runtime_structure.register_merge(
                parents, candidate["argument_ids"], timestamp, step, trigger
            )
            if not created:
                return []
            change = {
                "operation": "merge",
                "retired_viewpoints": parents,
                "created_viewpoints": [created],
                "argument_groups": [candidate["argument_ids"]],
                "score": score,
                "persistent_steps": persistent,
            }
        self._structure_candidate_streaks.clear()
        return [change]

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

    def _adjust_reasoning_for_institutional_actions(
        self,
        traces: list[ReasoningTrace],
        actions: list[dict[str, Any]],
    ) -> None:
        for trace in traces:
            for action in actions:
                if action.get("target_argument_id") != trace.argument_id:
                    continue
                if action["action_type"] in {"CLARIFY_NORM", "CLARIFY_AUTHORITY"}:
                    value = self.core_config.reasoning.observed_evidence_action
                    trace.supporting_factors.append({
                        "factor": f"observed_{action['action_type'].lower()}",
                        "value": value,
                        "action_id": action["action_id"],
                    })
                elif action["action_type"] == "CHALLENGE_INVALID_GROUNDING":
                    value = -self.core_config.reasoning.observed_challenge_action
                    trace.attacking_factors.append({
                        "factor": "observed_challenge_invalid_grounding",
                        "value": value,
                        "action_id": action["action_id"],
                    })
                else:
                    continue
                trace.score_after = rounded(trace.score_after + value)
                if trace.score_after >= self.core_config.accepted_threshold:
                    trace.recommended_status = "accepted"
                elif trace.score_after <= self.core_config.rejected_threshold:
                    trace.recommended_status = "rejected"
                else:
                    trace.recommended_status = "undecided"
                trace.reason += " Institutional action được diễn giải qua Society revision pipeline."

    @staticmethod
    def _normalized_for_revision(interactions: list[InteractionRecord]) -> list[InteractionRecord]:
        mapping = {
            "CLARIFY_NORM": "PROVIDE_EVIDENCE",
            "CLARIFY_AUTHORITY": "PROVIDE_EVIDENCE",
            "CHALLENGE_INVALID_GROUNDING": "CHALLENGE",
        }
        return [replace(row, action_type=mapping.get(row.action_type, row.action_type)) for row in interactions]

    def _policy_for(self, agent: ArgumentativeAgent):
        if self.config.ablations.institutional_policy and agent.kind == "contextual":
            return self.institutional_policy
        return self.ordinary_policy

    def run(self, verbose: bool = False) -> dict[str, Any]:
        agents = initialize_agents(self.base_mapping, self.snapshots[0], self.core_config)
        protocol = InteractionProtocol(agents, self.argument_owner, self.source_ids)
        timestamp_order = [row["timestamp"]["timestamp_id"] for row in self.snapshots]
        timestamp_runs: list[dict[str, Any]] = []
        full_log: list[str] = []
        all_events: list[dict[str, Any]] = []

        for timestamp_index, snapshot in enumerate(self.snapshots):
            timestamp = snapshot["timestamp"]["timestamp_id"]
            if timestamp_index:
                sync_agents_to_snapshot(agents, snapshot, self.base_mapping, self.core_config)
            used_signatures: set[tuple] = set()
            prior_interactions: list[InteractionRecord] = []
            cumulative_interactions: list[InteractionRecord] = []
            seen_hashes = {self._state_hash(agents)}
            no_change_steps = 0
            steps: list[dict[str, Any]] = []
            stop_reason = "max_steps_reached"

            for k in range(self.core_config.max_deliberation_steps):
                observations = {
                    agent_id: self.observer.build(agent, snapshot, k, prior_interactions)
                    for agent_id, agent in sorted(agents.items())
                }
                reasoning = {
                    agent_id: self.reasoner.evaluate(agent, observations[agent_id], snapshot)
                    for agent_id, agent in sorted(agents.items())
                }
                for agent_id, observation in observations.items():
                    self._adjust_reasoning_for_institutional_actions(
                        reasoning[agent_id], observation.other_agent_actions
                    )
                candidate_actions = {}
                institutional_audit = []
                for agent_id, agent in sorted(agents.items()):
                    policy = self._policy_for(agent)
                    candidate_actions[agent_id] = policy.candidates(
                        agent, observations[agent_id], reasoning[agent_id], snapshot
                    )
                selected = {}
                for agent_id, agent in sorted(agents.items()):
                    policy = self._policy_for(agent)
                    action = policy.select(candidate_actions[agent_id], used_signatures)
                    restriction_valid, restriction_reason = True, "ordinary viewpoint policy"
                    if policy is self.institutional_policy:
                        restriction_valid, restriction_reason = policy.validate_restrictions(action)
                        institutional_audit.append({
                            "agent_id": agent_id,
                            "action_id": action.action_id,
                            "action_type": action.action_type,
                            "valid": restriction_valid,
                            "reason": restriction_reason,
                        })
                    if restriction_valid:
                        protocol.validate(action, snapshot, used_signatures)
                    else:
                        action.valid, action.validation_reason = False, restriction_reason
                    if not action.valid:
                        action = next(
                            row for row in candidate_actions[agent_id]
                            if row.action_type == ActionType.NO_OP.value
                        )
                        protocol.validate(action, snapshot, used_signatures)
                    selected[agent_id] = action
                interactions = protocol.execute(list(selected.values()))
                for interaction in interactions:
                    used_signatures.add(selected[interaction.actor_agent].signature())
                cumulative_interactions.extend(interactions)

                # Preserve the core layer's heuristic traces for audit/UI comparison, while
                # letting society semantics participate explicitly in belief revision.
                heuristic_scores = {
                    trace.argument_id: trace.score_after
                    for traces in reasoning.values() for trace in traces
                }
                semantic_result = self.semantics.evaluate(heuristic_scores, snapshot["relations"])
                revision_reasoning = deepcopy(reasoning)
                blend = self.config.semantic_revision_blend
                for traces in revision_reasoning.values():
                    for trace in traces:
                        semantic_row = semantic_result["results"][trace.argument_id]
                        revision_score = rounded(
                            (1.0 - blend) * trace.score_after
                            + blend * semantic_row["semantic_score"]
                        )
                        semantic_row["revision_blend_score"] = revision_score
                        semantic_row["revision_blend_coefficient"] = blend
                        trace.score_after = revision_score
                        if revision_score >= self.core_config.accepted_threshold:
                            trace.recommended_status = "accepted"
                        elif revision_score <= self.core_config.rejected_threshold:
                            trace.recommended_status = "rejected"
                        else:
                            trace.recommended_status = "undecided"
                        trace.reason += (
                            f" Society revision blends the heuristic and semantic scores "
                            f"with coefficient {blend:.2f}."
                        )
                revisions = self.reviser.apply(
                    agents, observations, revision_reasoning,
                    self._normalized_for_revision(interactions), timestamp, k,
                )
                for agent in agents.values():
                    agent.state_history.append({"timestamp": timestamp, "step": k, "state": agent.snapshot_state()})

                all_no_op = all(row.action_type == ActionType.NO_OP.value for row in selected.values())
                state_hash = self._state_hash(agents)
                repeated_state = state_hash in seen_hashes
                no_change_steps = no_change_steps + 1 if not revisions else 0
                no_change_stop = no_change_steps >= self.core_config.no_change_patience and repeated_state
                will_stop = all_no_op or no_change_stop
                core_metrics = self.core_metrics.compute(
                    agents, interactions, revisions, cumulative_interactions, converged=will_stop
                )
                agent_states = {key: value.snapshot_state() for key, value in sorted(agents.items())}
                runtime_states = self.runtime_structure.materialize_agent_states(agent_states)
                viewpoint_result = self.viewpoint_dynamics.compute(
                    runtime_states, snapshot["relations"]
                )
                if not self.config.ablations.viewpoint_dynamics:
                    viewpoint_result["split_candidates"] = []
                    viewpoint_result["merge_candidates"] = []
                viewpoint_result["applied_changes"] = self._apply_runtime_structure_change(
                    viewpoint_result, runtime_states, timestamp, k
                )
                interaction_dicts = [row.to_dict() for row in interactions]
                cumulative_dicts = [row.to_dict() for row in cumulative_interactions]
                prevalence_result = self.prevalence.compute(
                    agent_states, cumulative_dicts, snapshot["relations"], self.argument_catalog,
                    timestamp_order, timestamp,
                )
                society_metrics = self.dynamic_metrics.compute(
                    agent_states, interaction_dicts, cumulative_dicts, core_metrics,
                    semantic_result, viewpoint_result, prevalence_result,
                )
                events = self.dynamics.detect(timestamp, k, society_metrics, interaction_dicts)
                all_events.extend(events)
                step_record = {
                    "timestamp": timestamp,
                    "deliberation_step": k,
                    "observations": {key: value.to_dict() for key, value in observations.items()},
                    "reasoning_traces": {key: [row.to_dict() for row in value] for key, value in reasoning.items()},
                    "candidate_actions": {key: [row.to_dict() for row in value] for key, value in candidate_actions.items()},
                    "selected_actions": {key: value.to_dict() for key, value in selected.items()},
                    "interactions": interaction_dicts,
                    "belief_revisions": [row.to_dict() for row in revisions],
                    "core_metrics": core_metrics,
                    "agent_states_after": agent_states,
                    "state_hash": state_hash,
                    "argumentation_semantics": semantic_result,
                    "viewpoint_dynamics": viewpoint_result,
                    "structural_prevalence": prevalence_result,
                    "society_metrics": society_metrics,
                    "society_events": events,
                    "runtime_society_structure": self.runtime_structure.snapshot(),
                    "institutional_protocol_audit": institutional_audit,
                }
                step_record["log"] = society_step_log(step_record)
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
                steps[-1]["society_metrics"]["simulation_convergence"] = False
            timestamp_runs.append({
                "timestamp": timestamp,
                "temporal_context": snapshot["timestamp"],
                "steps": steps,
                "stop_reason": stop_reason,
                "steps_executed": len(steps),
                "final_agent_states": {key: value.snapshot_state() for key, value in sorted(agents.items())},
            })

        result = {
            "schema_version": "vip-girls-society-trace-1.0",
            "model": "Dynamic Agent Society with Argumentation Semantics and Emergent Dynamics",
            "time_semantics": {
                "t": "real-world information timestamp",
                "k": "deliberation iteration inside t",
                "society_event": "typed structural event, not a third numeric clock",
            },
            "config": self.config.to_dict(),
            "base_viewpoint_mapping": self.base_mapping,
            "argument_owner": dict(sorted(self.argument_owner.items())),
            "argument_owners": dict(sorted(self.argument_owners.items())),
            "argument_catalog": self.argument_catalog,
            "timestamps": timestamp_runs,
            "society_events": all_events,
            "dominance_history": self.dynamics.history(),
            "final_runtime_society_structure": self.runtime_structure.snapshot(),
            "supported_agent_types": {
                "collective": "instantiated",
                "contextual_institutional": "instantiated with restricted policy",
                "personal": "type supported, not instantiated in current case",
                "organization": "type supported, not instantiated in current case",
            },
            "deterministic_log": full_log,
            "limitations": [
                "Structural proxies are not measurements of real public support or validated social phenomena.",
                "Consensus proxy is separate from simulation convergence and does not establish social consensus.",
                "The manual base mapping remains immutable; runtime split/merge creates and retires overlay viewpoints.",
                "Weighted bipolar semantics is an explainable baseline, not ASPIC+ and not factual truth.",
            ],
        }
        result["risk_monitoring"] = RiskMonitoringEngine(
            self.data, self.snapshots, result, self.config
        ).build()
        if verbose:
            print("\n".join(full_log))
        return result
