from __future__ import annotations

from typing import Any

from bluesky.v3.simulation_v3 import DynamicSocietySimulation

from .config_v4 import DEFAULT_V4_CONFIG, V4Config
from .hierarchy import AgentHierarchy
from .prioritization_v4 import V4RiskMonitoringEngine
from .propagation import ACTION_TO_MESSAGE, DeterministicMessageQueue


class HierarchicalArgumentSocietySimulation:
    """V4 adapter over V3 with explicit subagents and delivery-gated observation."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        config: V4Config = DEFAULT_V4_CONFIG,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config

    def run(self, verbose: bool = False) -> dict[str, Any]:
        trace = DynamicSocietySimulation(
            self.data, self.snapshots, self.config.v3
        ).run(verbose=verbose)
        v3_risk = trace["risk_monitoring"]
        hierarchy = AgentHierarchy(self.data, trace["argument_catalog"])
        queue = DeterministicMessageQueue(
            [run["timestamp"] for run in trace["timestamps"]],
            self.config.propagation,
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
                hierarchy.sync_from_v3_step(step)
                delivered_before = queue.deliver(timestamp, k, hierarchy.subagents)
                observations: dict[str, list[str]] = {}
                local_revisions: list[dict[str, Any]] = []
                for argument_id, agent in sorted(hierarchy.subagents.items()):
                    consumed = queue.consume(agent, timestamp, k)
                    if consumed:
                        observations[agent.agent_id] = [item.message_id for item in consumed]
                        local_revisions.extend(hierarchy.observe_and_revise(
                            argument_id, consumed, timestamp, k,
                            self.config.v3.effective_v2_config(),
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
                            self.config.v3.effective_v2_config(),
                        ))

                macros = hierarchy.aggregate(step, snapshot["relations"])
                macro_dict = {key: value.to_dict() for key, value in sorted(macros.items())}
                for candidate in step["viewpoint_dynamics"]["split_candidates"]:
                    candidate["argument_agent_contributors"] = macro_dict[
                        candidate["agent_id"]
                    ]["split_contributors"]
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
                    interaction["v3_protocol_delivered"] = interaction["delivered"]
                    interaction["v4_propagation"] = (
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
            "schema_version": "agora-v4-trace-1.0",
            "model": "Hierarchical Argumentative Agent Society with Asynchronous Information Propagation",
            "v3_config": trace["config"],
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
                    "grounded V3 actions create messages",
                    "zero-delay messages may deliver in the same k",
                    "argument-agent beliefs revise",
                    "viewpoint macro state aggregates",
                    "society metrics/events remain V3 baseline",
                ],
                "cross_snapshot_rule": (
                    "Nếu available k vượt số bước của t, chuyển deterministic sang (t_next,k0); "
                    "Steering dùng cùng quy tắc carry này."
                ),
                "real_world_exposure": "unknown",
                "limitation": (
                    "Độ trễ là giả định sensitivity, không phải số đo ngoài đời thực; "
                    "V4 nới giả định thông tin đồng bộ chứ không tuyên bố mô phỏng thực tế."
                ),
            },
        })
        trace["risk_monitoring"] = V4RiskMonitoringEngine(
            self.data, self.snapshots, trace, self.config
        ).build()
        trace["v3_zero_delay_comparison"] = self._risk_comparison(
            v3_risk, trace["risk_monitoring"]
        )
        trace["limitations"] = list(trace["limitations"]) + [
            "Argument subagents reuse deterministic V2 action weights; they are not persons or measured audiences.",
            "Grounded action selection remains inherited from the V3 viewpoint policy; V4 adds explicit local delivery and revision traces.",
            "Real-world exposure is unknown unless future source data explicitly establishes it.",
        ]
        return trace

    @staticmethod
    def _risk_comparison(v3: dict[str, Any], v4: dict[str, Any]) -> dict[str, Any]:
        window_id = "t1__t6"
        old = {row["argument_id"]: row for row in v3["by_window"][window_id]["ranked_arguments"]}
        new = {row["argument_id"]: row for row in v4["by_window"][window_id]["ranked_arguments"]}
        return {
            "window_id": window_id,
            "steering_changed": any(
                old[key]["steering_score"] != new[key]["steering_score"] for key in old
            ),
            "risk_changed": any(old[key]["risk_score"] != new[key]["risk_score"] for key in old),
            "conflict_unchanged": all(
                old[key]["conflict_score"] == new[key]["conflict_score"] for key in old
            ),
            "v3_rank": [row["argument_id"] for row in v3["by_window"][window_id]["ranked_arguments"]],
            "v4_rank": [row["argument_id"] for row in v4["by_window"][window_id]["ranked_arguments"]],
        }
