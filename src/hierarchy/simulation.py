from __future__ import annotations

from typing import Any

from society.simulation import DynamicSocietySimulation

from .config import DEFAULT_HIERARCHY_CONFIG, HierarchyConfig
from .hierarchy import AgentHierarchy
from .prioritization import ArrivalAwareRiskMonitoringEngine
from .propagation import ACTION_TO_MESSAGE, DeterministicMessageQueue


class HierarchicalArgumentSocietySimulation:
    """Hierarchy adapter over the dynamic society with explicit subagents and delivery-gated observation."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        config: HierarchyConfig = DEFAULT_HIERARCHY_CONFIG,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config

    def run(self, verbose: bool = False) -> dict[str, Any]:
        trace = DynamicSocietySimulation(
            self.data, self.snapshots, self.config.society
        ).run(verbose=verbose)
        baseline_risk = trace["risk_monitoring"]
        hierarchy = AgentHierarchy(self.data, trace["argument_catalog"])
        queue = DeterministicMessageQueue(
            [run["timestamp"] for run in trace["timestamps"]],
            self.config.propagation,
            {
                run["timestamp"]: len(run["steps"])
                for run in trace["timestamps"]
            },
        )
        snapshot_by_t = {
            snapshot["timestamp"]["timestamp_id"]: snapshot for snapshot in self.snapshots
        }
        introduced_sent: set[str] = set()
        propagation_steps: list[dict[str, Any]] = []

        for run in trace["timestamps"]:
            timestamp = run["timestamp"]
            snapshot = snapshot_by_t[timestamp]
            steps_in_t = len(run["steps"])
            for step in run["steps"]:
                k = step["deliberation_step"]
                hierarchy.sync_from_society_step(step)
                delivered_before = queue.deliver(timestamp, k, hierarchy.subagents)
                observations: dict[str, list[str]] = {}
                local_revisions: list[dict[str, Any]] = []
                for argument_id, agent in sorted(hierarchy.subagents.items()):
                    consumed = queue.consume(agent, timestamp, k)
                    if consumed:
                        observations[agent.agent_id] = [item.message_id for item in consumed]
                        local_revisions.extend(hierarchy.observe_and_revise(
                            argument_id, consumed, timestamp, k,
                            self.config.society.effective_core_config(),
                        ))

                sent = []
                if k == 0:
                    for argument in snapshot["arguments"]:
                        argument_id = argument["id"]
                        if argument["newly_introduced"] and argument_id not in introduced_sent:
                            sent.append(queue.send_argument_available(
                                hierarchy.subagents[argument_id], timestamp, k, steps_in_t
                            ))
                            introduced_sent.add(argument_id)
                for interaction in step["interactions"]:
                    if interaction["action_type"] not in ACTION_TO_MESSAGE:
                        continue
                    source_id = interaction.get("source_argument_id")
                    target_id = interaction.get("target_argument_id")
                    if interaction["action_type"] == "RETRACT":
                        target_id = source_id
                    if not source_id or not target_id:
                        continue
                    sent.append(queue.send_from_interaction(
                        interaction,
                        hierarchy.subagents[source_id],
                        hierarchy.subagents[target_id],
                        steps_in_t,
                    ))

                delivered_after = queue.deliver(timestamp, k, hierarchy.subagents)
                for argument_id, agent in sorted(hierarchy.subagents.items()):
                    consumed = queue.consume(agent, timestamp, k)
                    if consumed:
                        observations.setdefault(agent.agent_id, []).extend(
                            item.message_id for item in consumed
                        )
                        local_revisions.extend(hierarchy.observe_and_revise(
                            argument_id, consumed, timestamp, k,
                            self.config.society.effective_core_config(),
                        ))

                macros = hierarchy.aggregate(step, snapshot["relations"])
                macro_dict = {key: value.to_dict() for key, value in sorted(macros.items())}
                for candidate in step["viewpoint_dynamics"]["split_candidates"]:
                    macro = macro_dict.get(candidate["agent_id"])
                    candidate["argument_agent_contributors"] = (
                        macro["split_contributors"] if macro else [
                            {
                                "argument_id": argument_id,
                                "confidence": hierarchy.subagents[argument_id].confidence,
                                "belief_status": hierarchy.subagents[argument_id].belief_status,
                            }
                            for argument_id in candidate["argument_ids"][:3]
                        ]
                    )
                visible_states = {
                    agent.agent_id: agent.to_dict()
                    for agent in hierarchy.subagents.values()
                    if int(agent.introduced_at[1:]) <= int(timestamp[1:])
                }
                step["argument_agent_observations"] = observations
                step["argument_agent_revisions"] = local_revisions
                step["argument_subagents"] = visible_states
                step["viewpoint_macro_agents"] = macro_dict
                step["message_events"] = {
                    "delivered_before_observation": [item.message_id for item in delivered_before],
                    "sent_after_action": [item.message_id for item in sent],
                    "delivered_after_action_zero_delay": [item.message_id for item in delivered_after],
                    "consumed": sorted({
                        message_id for rows in observations.values() for message_id in rows
                    }),
                    "pending_count": len(queue.pending),
                }
                propagation_steps.append({
                    "timestamp": timestamp,
                    "deliberation_step": k,
                    **step["message_events"],
                })

        message_by_interaction = {
            message.provenance.get("interaction_id"): message
            for message in queue.messages
            if message.provenance.get("interaction_id")
        }
        for run in trace["timestamps"]:
            for step in run["steps"]:
                for interaction in step["interactions"]:
                    message = message_by_interaction.get(interaction["interaction_id"])
                    interaction["baseline_protocol_delivered"] = interaction["delivered"]
                    interaction["hierarchy_propagation"] = (
                        {
                            "message_id": message.message_id,
                            "delivery_status": message.delivery_status,
                            "available_at_t": message.available_at_t,
                            "available_at_k": message.available_at_k,
                            "delivered_at_t": message.delivered_at_t,
                            "delivered_at_k": message.delivered_at_k,
                            "observable_only_after_delivery": True,
                        }
                        if message else None
                    )

        trace.update({
            "schema_version": "vip-girls-hierarchy-trace-1.0",
            "model": "Hierarchical Argumentative Agent Society with Asynchronous Information Propagation",
            "society_config": trace["config"],
            "config": self.config.to_dict(),
            "agent_hierarchy": hierarchy.trace_mapping(),
            "argument_relations_by_timestamp": {
                snapshot["timestamp"]["timestamp_id"]: snapshot["relations"]
                for snapshot in self.snapshots
            },
            "argument_subagents": {
                agent.agent_id: agent.to_dict()
                for agent in hierarchy.subagents.values()
            },
            "message_trace": queue.snapshot(),
            "propagation_trace": propagation_steps,
            "propagation_assumption": {
                "mode": self.config.propagation.mode,
                "default_delay_steps": self.config.propagation.default_delay_steps,
                "unit": "k (logical deliberation step)",
                "sequence": [
                    "deliver eligible messages",
                    "argument agents observe delivered inbox",
                    "argument agents reason deterministically",
                    "grounded society actions create messages",
                    "zero-delay messages may deliver in the same k",
                    "argument-agent beliefs revise",
                    "viewpoint macro state aggregates",
                    "society metrics/events remain society baseline",
                ],
                "cross_snapshot_rule": (
                    "Delay được trừ tuần tự theo số bước thực của từng snapshot; "
                    "message có thể đi qua nhiều snapshot và giữ phần delay dư."
                ),
                "real_world_exposure": "unknown",
                "limitation": (
                    "Độ trễ là giả định sensitivity, không phải số đo ngoài đời thực; "
                    "Hierarchy layer nới giả định thông tin đồng bộ chứ không tuyên bố mô phỏng thực tế."
                ),
            },
        })
        trace["risk_monitoring"] = ArrivalAwareRiskMonitoringEngine(
            self.data, self.snapshots, trace, self.config
        ).build()
        trace["zero_delay_baseline_comparison"] = self._risk_comparison(
            baseline_risk, trace["risk_monitoring"]
        )
        trace["limitations"] = list(trace["limitations"]) + [
            "Argument subagents reuse deterministic core action weights; they are not persons or measured audiences.",
            "Grounded action selection remains inherited from the society viewpoint policy; Hierarchy layer adds explicit local delivery and revision traces.",
            "Real-world exposure is unknown unless future source data explicitly establishes it.",
        ]
        return trace

    @staticmethod
    def _risk_comparison(baseline: dict[str, Any], arrival_aware: dict[str, Any]) -> dict[str, Any]:
        window_id = "t1__t6"
        old = {row["argument_id"]: row for row in baseline["by_window"][window_id]["ranked_arguments"]}
        new = {row["argument_id"]: row for row in arrival_aware["by_window"][window_id]["ranked_arguments"]}
        return {
            "window_id": window_id,
            "steering_changed": any(
                old[key]["steering_score"] != new[key]["steering_score"] for key in old
            ),
            "risk_changed": any(old[key]["risk_score"] != new[key]["risk_score"] for key in old),
            "conflict_unchanged": all(
                old[key]["conflict_score"] == new[key]["conflict_score"] for key in old
            ),
            "baseline_rank": [row["argument_id"] for row in baseline["by_window"][window_id]["ranked_arguments"]],
            "arrival_aware_rank": [row["argument_id"] for row in arrival_aware["by_window"][window_id]["ranked_arguments"]],
        }
