from __future__ import annotations

from typing import Any

from .config_v4 import PropagationConfig
from .models import ArgumentSubAgent, InformationMessage


ACTION_TO_MESSAGE = {
    "PRESENT_ARGUMENT": "ARGUMENT_AVAILABLE",
    "SUPPORT": "SUPPORT",
    "ATTACK": "ATTACK",
    "CHALLENGE": "CHALLENGE",
    "CHALLENGE_INVALID_GROUNDING": "CHALLENGE",
    "PROVIDE_EVIDENCE": "PROVIDE_EVIDENCE",
    "CLARIFY_NORM": "PROVIDE_EVIDENCE",
    "CLARIFY_AUTHORITY": "PROVIDE_EVIDENCE",
    "RETRACT": "RETRACTION",
}


class DeterministicMessageQueue:
    """Queue ordered by logical (t, k, message_id), without calendar invention."""

    def __init__(self, timestamp_order: list[str], config: PropagationConfig) -> None:
        self.order = {timestamp: index for index, timestamp in enumerate(timestamp_order)}
        self.timestamps = timestamp_order
        self.config = config
        self.pending: list[InformationMessage] = []
        self.messages: list[InformationMessage] = []

    def _schedule(self, sent_t: str, sent_k: int, delay: int, steps_in_t: int) -> tuple[str, int, bool]:
        available_k = sent_k + delay
        if available_k < steps_in_t:
            return sent_t, available_k, False
        if not self.config.carry_across_snapshots:
            return sent_t, available_k, False
        next_index = self.order[sent_t] + 1
        if next_index >= len(self.timestamps):
            return sent_t, available_k, False
        return self.timestamps[next_index], 0, True

    def send_from_interaction(
        self,
        interaction: dict[str, Any],
        source_agent: ArgumentSubAgent,
        target_agent: ArgumentSubAgent,
        steps_in_t: int,
    ) -> InformationMessage:
        message_type = ACTION_TO_MESSAGE[interaction["action_type"]]
        delay = self.config.delay_for(message_type)
        available_t, available_k, crossed = self._schedule(
            interaction["timestamp"], interaction["deliberation_step"], delay, steps_in_t
        )
        message = InformationMessage(
            message_id=f"MSG-{len(self.messages) + 1:05d}",
            source_agent_id=source_agent.agent_id,
            source_argument_id=source_agent.argument_id,
            target_agent_id=target_agent.agent_id,
            target_argument_id=target_agent.argument_id,
            message_type=message_type,
            sent_at_t=interaction["timestamp"],
            sent_at_k=interaction["deliberation_step"],
            delay_steps=delay,
            available_at_t=available_t,
            available_at_k=available_k,
            crossed_snapshot_boundary=crossed,
            relation_ids=list(interaction["relation_ids"]),
            source_ids=list(interaction["evidence_source_ids"]),
            provenance={
                "interaction_id": interaction["interaction_id"],
                "action_id": interaction["action_id"],
                "argument_ids": list(interaction["provenance"]["argument_ids"]),
                "relation_ids": list(interaction["relation_ids"]),
                "source_ids": list(interaction["evidence_source_ids"]),
                "real_world_exposure": "unknown",
            },
        )
        self.messages.append(message)
        self.pending.append(message)
        self.pending.sort(key=self._sort_key)
        source_agent.action_history.append({
            "message_id": message.message_id,
            "message_type": message.message_type,
            "sent_at_t": message.sent_at_t,
            "sent_at_k": message.sent_at_k,
        })
        return message

    def send_argument_available(
        self,
        argument: ArgumentSubAgent,
        timestamp: str,
        step: int,
        steps_in_t: int,
    ) -> InformationMessage:
        delay = self.config.delay_for("ARGUMENT_AVAILABLE")
        available_t, available_k, crossed = self._schedule(timestamp, step, delay, steps_in_t)
        message = InformationMessage(
            message_id=f"MSG-{len(self.messages) + 1:05d}",
            source_agent_id=argument.agent_id,
            source_argument_id=argument.argument_id,
            target_agent_id=argument.agent_id,
            target_argument_id=argument.argument_id,
            message_type="ARGUMENT_AVAILABLE",
            sent_at_t=timestamp,
            sent_at_k=step,
            delay_steps=delay,
            available_at_t=available_t,
            available_at_k=available_k,
            crossed_snapshot_boundary=crossed,
            source_ids=list(argument.source_ids),
            provenance={
                "argument_ids": [argument.argument_id],
                "relation_ids": [],
                "source_ids": list(argument.source_ids),
                "canonical_introduction": argument.introduced_at,
                "real_world_exposure": "unknown",
            },
        )
        self.messages.append(message)
        self.pending.append(message)
        self.pending.sort(key=self._sort_key)
        return message

    def _sort_key(self, message: InformationMessage) -> tuple[int, int, str]:
        return (self.order[message.available_at_t], message.available_at_k, message.message_id)

    def deliver(self, timestamp: str, step: int, agents: dict[str, ArgumentSubAgent]) -> list[InformationMessage]:
        now = (self.order[timestamp], step)
        delivered: list[InformationMessage] = []
        remaining: list[InformationMessage] = []
        for message in self.pending:
            due = (self.order[message.available_at_t], message.available_at_k)
            if due <= now:
                message.delivery_status = "delivered"
                message.delivered_at_t = timestamp
                message.delivered_at_k = step
                agents[message.target_argument_id].inbox.append(message.message_id)
                delivered.append(message)
            else:
                remaining.append(message)
        self.pending = remaining
        return delivered

    def consume(self, agent: ArgumentSubAgent, timestamp: str, step: int) -> list[InformationMessage]:
        by_id = {message.message_id: message for message in self.messages}
        consumed: list[InformationMessage] = []
        for message_id in list(agent.inbox):
            message = by_id[message_id]
            if message.delivery_status != "delivered":
                continue
            message.delivery_status = "consumed"
            message.consumed_at_t = timestamp
            message.consumed_at_k = step
            agent.inbox.remove(message_id)
            agent.observed_message_ids.append(message_id)
            consumed.append(message)
        return consumed

    def snapshot(self) -> list[dict[str, Any]]:
        return [message.to_dict() for message in self.messages]
