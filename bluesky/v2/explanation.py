from __future__ import annotations

from typing import Any


def concise_step_log(step: dict[str, Any]) -> list[str]:
    prefix = f"[{step['timestamp']}:k{step['deliberation_step']}]"
    lines: list[str] = []
    for agent_id, observation in sorted(step["observations"].items()):
        observed = len(observation["other_agent_actions"]) + len(observation["newly_introduced_arguments"])
        lines.append(f"{prefix} {agent_id} OBSERVE {observed} salient item(s)")
        traces = step["reasoning_traces"].get(agent_id, [])
        if traces:
            strongest = max(traces, key=lambda row: (row["score_after"], row["argument_id"]))
            lines.append(f"{prefix} {agent_id} REASON {strongest['argument_id']}={strongest['score_after']:.4f}")
        action = step["selected_actions"].get(agent_id)
        if action:
            lines.append(f"{prefix} {agent_id} SELECT {action['action_type']} {action.get('target_agent') or ''}".rstrip())
    for interaction in step["interactions"]:
        lines.append(
            f"{prefix} {interaction['actor_agent']} -> {interaction.get('target_agent') or 'SELF'} "
            f"{interaction['action_type']} via {','.join(interaction['relation_ids']) or interaction.get('source_argument_id','')}"
        )
    for revision in step["belief_revisions"]:
        lines.append(
            f"{prefix} {revision['agent_id']} REVISE {revision['argument_id']} "
            f"{revision['old_confidence']:.4f}->{revision['new_confidence']:.4f}"
        )
    return lines
