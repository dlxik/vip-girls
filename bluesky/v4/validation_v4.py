from __future__ import annotations

from typing import Any

from bluesky.v3.validation_v3 import validate_v3_trace


def validate_v4_trace(
    trace: dict[str, Any], data: dict[str, Any], snapshots: list[dict[str, Any]]
) -> dict[str, int]:
    counts = validate_v3_trace(trace, data, snapshots)
    canonical_ids = {row["final_arg_id"] for row in data["selected"]}
    mapped = {
        argument_id: viewpoint["viewpoint_id"]
        for viewpoint in data["viewpoint_mapping"]["viewpoints"]
        for argument_id in viewpoint["argument_ids"]
    }
    errors: list[str] = []
    subagents = trace["argument_subagents"]
    if len(subagents) != len(canonical_ids):
        errors.append("Không có đúng một subagent cho mỗi selected argument")
    argument_ids = [row["argument_id"] for row in subagents.values()]
    if set(argument_ids) != canonical_ids or len(argument_ids) != len(set(argument_ids)):
        errors.append("Subagent ownership không phủ duy nhất canonical arguments")
    for row in subagents.values():
        if row["parent_viewpoint_id"] != mapped[row["argument_id"]]:
            errors.append(f"Sai parent viewpoint: {row['agent_id']}")
    seen: set[str] = set()
    order = {row["timestamp_id"]: index for index, row in enumerate(data["timeline"])}
    for message in trace["message_trace"]:
        if message["message_id"] in seen:
            errors.append(f"Message ID trùng: {message['message_id']}")
        seen.add(message["message_id"])
        if message["delay_steps"] < 0:
            errors.append(f"Delay âm: {message['message_id']}")
        if message["delivered_at_t"] is not None:
            available = (order[message["available_at_t"]], message["available_at_k"])
            delivered = (order[message["delivered_at_t"]], message["delivered_at_k"])
            if delivered < available:
                errors.append(f"Deliver trước available: {message['message_id']}")
        if message["provenance"].get("real_world_exposure") != "unknown":
            errors.append(f"Exposure bị suy diễn: {message['message_id']}")
    expected_windows = len(data["timeline"]) * (len(data["timeline"]) + 1) // 2
    if len(trace["risk_monitoring"]["by_window"]) != expected_windows:
        errors.append("Không bảo toàn đủ snapshot windows")
    for window in trace["risk_monitoring"]["by_window"].values():
        for row in window["ranked_arguments"]:
            for pair in row["steering_evidence"]["pairwise_influence"]:
                if pair["I"] != round(pair["T_delta"] * pair["L"] * pair["P"], 4):
                    errors.append("Sai công thức I_V4")
                if pair["real_world_exposure"] != "unknown":
                    errors.append("Steering suy diễn exposure thực")
    if errors:
        raise ValueError("V4 trace không hợp lệ:\n- " + "\n- ".join(errors))
    return {
        **counts,
        "argument_subagents": len(subagents),
        "messages": len(trace["message_trace"]),
        "v4_risk_windows": expected_windows,
    }
