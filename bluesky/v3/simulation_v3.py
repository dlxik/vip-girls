from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

from bluesky.v2.agent import ArgumentativeAgent, initialize_agents, sync_agents_to_snapshot
from bluesky.v2.belief_revision import BeliefRevisionEngine
from bluesky.v2.interaction import InteractionProtocol
from bluesky.v2.metrics import SocietyMetrics
from bluesky.v2.models import ActionType, InteractionRecord, ReasoningTrace, rounded
from bluesky.v2.observation import ObservationBuilder
from bluesky.v2.policy import RuleBasedArgumentationPolicy
from bluesky.v2.reasoning import WeightedArgumentReasoner

from .config_v3 import DEFAULT_V3_CONFIG, V3Config
from .explanation_v3 import society_step_log
from .institutional_policy import InstitutionalActionPolicy
from .metrics_v3 import SocietyMetricsV3
from .prevalence import StructuralPrevalenceCalculator
from .prioritization import RiskMonitoringEngine
from .semantics import WeightedBipolarSemantics
from .society_dynamics import SocietyDynamicsEngine
from .viewpoint_dynamics import RuntimeSocietyStructure, ViewpointDynamics


class DynamicSocietySimulation:
    """V3 orchestration reusing V1 snapshots and V2 agent-level engines."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        config: V3Config = DEFAULT_V3_CONFIG,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config
        self.v2_config = config.effective_v2_config()
        self.base_mapping = deepcopy(data["viewpoint_mapping"])
        self.argument_owner = {
            argument_id: row["viewpoint_id"]
            for row in self.base_mapping["viewpoints"]
            for argument_id in row["argument_ids"]
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
        self.reasoner = WeightedArgumentReasoner(self.v2_config, data["sources"])
        self.ordinary_policy = RuleBasedArgumentationPolicy(self.v2_config, self.argument_owner)
        self.institutional_policy = InstitutionalActionPolicy(
            self.argument_owner, data["sources"], self.argument_catalog
        )
        self.reviser = BeliefRevisionEngine(self.v2_config)
        self.v2_metrics = SocietyMetrics()
        self.semantics = WeightedBipolarSemantics(
            config.semantics,
            self.v2_config.reasoning.relation_confidence,
            use_relation_confidence=config.ablations.relation_confidence,
        )
        self.viewpoint_dynamics = ViewpointDynamics(config.viewpoint_dynamics, self.argument_catalog)
        self.prevalence = StructuralPrevalenceCalculator()
        self.v3_metrics = SocietyMetricsV3()
        self.dynamics = SocietyDynamicsEngine(config.dynamics, config.viewpoint_dynamics)
        self.runtime_structure = RuntimeSocietyStructure(self.base_mapping)

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
                    value = self.v2_config.reasoning.observed_evidence_action
                    trace.supporting_factors.append({
                        "factor": f"observed_{action['action_type'].lower()}",
                        "value": value,
                        "action_id": action["action_id"],
                    })
                elif action["action_type"] == "CHALLENGE_INVALID_GROUNDING":
                    value = -self.v2_config.reasoning.observed_challenge_action
                    trace.attacking_factors.append({
                        "factor": "observed_challenge_invalid_grounding",
                        "value": value,
                        "action_id": action["action_id"],
                    })
                else:
                    continue
                trace.score_after = rounded(trace.score_after + value)
                if trace.score_after >= self.v2_config.accepted_threshold:
                    trace.recommended_status = "accepted"
                elif trace.score_after <= self.v2_config.rejected_threshold:
                    trace.recommended_status = "rejected"
                else:
                    trace.recommended_status = "undecided"
                trace.reason += " Institutional action được diễn giải qua V3 revision pipeline."

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
        agents = initialize_agents(self.base_mapping, self.snapshots[0], self.v2_config)
        protocol = InteractionProtocol(agents, self.argument_owner, self.source_ids)
        timestamp_order = [row["timestamp"]["timestamp_id"] for row in self.snapshots]
        timestamp_runs: list[dict[str, Any]] = []
        full_log: list[str] = []
        all_events: list[dict[str, Any]] = []

        for timestamp_index, snapshot in enumerate(self.snapshots):
            timestamp = snapshot["timestamp"]["timestamp_id"]
            if timestamp_index:
                sync_agents_to_snapshot(agents, snapshot, self.base_mapping, self.v2_config)
            used_signatures: set[tuple] = set()
            prior_interactions: list[InteractionRecord] = []
            cumulative_interactions: list[InteractionRecord] = []
            seen_hashes = {self._state_hash(agents)}
            no_change_steps = 0
            steps: list[dict[str, Any]] = []
            stop_reason = "max_steps_reached"

            for k in range(self.v2_config.max_deliberation_steps):
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

                # Preserve V2's heuristic traces for audit/UI comparison, while
                # letting V3 semantics participate explicitly in belief revision.
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
                        if revision_score >= self.v2_config.accepted_threshold:
                            trace.recommended_status = "accepted"
                        elif revision_score <= self.v2_config.rejected_threshold:
                            trace.recommended_status = "rejected"
                        else:
                            trace.recommended_status = "undecided"
                        trace.reason += (
                            f" V3 revision blends the heuristic and semantic scores "
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
                no_change_stop = no_change_steps >= self.v2_config.no_change_patience and repeated_state
                will_stop = all_no_op or no_change_stop
                v2_metrics = self.v2_metrics.compute(
                    agents, interactions, revisions, cumulative_interactions, converged=will_stop
                )
                agent_states = {key: value.snapshot_state() for key, value in sorted(agents.items())}
                viewpoint_result = self.viewpoint_dynamics.compute(agent_states, snapshot["relations"])
                if not self.config.ablations.viewpoint_dynamics:
                    viewpoint_result["split_candidates"] = []
                    viewpoint_result["merge_candidates"] = []
                interaction_dicts = [row.to_dict() for row in interactions]
                cumulative_dicts = [row.to_dict() for row in cumulative_interactions]
                prevalence_result = self.prevalence.compute(
                    agent_states, cumulative_dicts, snapshot["relations"], self.argument_catalog,
                    timestamp_order, timestamp,
                )
                metrics_v3 = self.v3_metrics.compute(
                    agent_states, interaction_dicts, cumulative_dicts, v2_metrics,
                    semantic_result, viewpoint_result, prevalence_result,
                )
                events = self.dynamics.detect(timestamp, k, metrics_v3, interaction_dicts)
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
                    "society_metrics": v2_metrics,
                    "agent_states_after": agent_states,
                    "state_hash": state_hash,
                    "argumentation_semantics": semantic_result,
                    "viewpoint_dynamics": viewpoint_result,
                    "structural_prevalence": prevalence_result,
                    "society_metrics_v3": metrics_v3,
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
                steps[-1]["society_metrics_v3"]["simulation_convergence"] = False
            timestamp_runs.append({
                "timestamp": timestamp,
                "temporal_context": snapshot["timestamp"],
                "steps": steps,
                "stop_reason": stop_reason,
                "steps_executed": len(steps),
                "final_agent_states": {key: value.snapshot_state() for key, value in sorted(agents.items())},
            })

        result = {
            "schema_version": "agora-v3-trace-1.0",
            "model": "Dynamic Agent Society with Argumentation Semantics and Emergent Dynamics",
            "time_semantics": {
                "t": "real-world information timestamp",
                "k": "deliberation iteration inside t",
                "society_event": "typed structural event, not a third numeric clock",
            },
            "config": self.config.to_dict(),
            "base_viewpoint_mapping": self.base_mapping,
            "argument_owner": dict(sorted(self.argument_owner.items())),
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
                "Viewpoint mapping remains a manual immutable base; runtime split/merge is disabled by default.",
                "Weighted bipolar semantics is an explainable baseline, not ASPIC+ and not factual truth.",
            ],
        }
        result["risk_monitoring"] = RiskMonitoringEngine(
            self.data, self.snapshots, result, self.config
        ).build()
        if verbose:
            print("\n".join(full_log))
        return result
