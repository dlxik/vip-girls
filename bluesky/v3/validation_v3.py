from __future__ import annotations

from typing import Any

from bluesky.v2.validation import validate_trace_provenance


def validate_v3_trace(
    trace: dict[str, Any], data: dict[str, Any], snapshots: list[dict[str, Any]]
) -> dict[str, int]:
    base_counts = validate_trace_provenance(trace, data, snapshots)
    argument_ids = {row["final_arg_id"] for row in data["selected"]}
    relation_ids = {row["relation_id"] for row in data["relations"]}
    source_ids = {row["source_id"] for row in data["sources"]}
    agent_ids = {row["viewpoint_id"] for row in data["viewpoint_mapping"]["viewpoints"]}
    errors: list[str] = []
    event_ids: set[str] = set()
    counts = {
        **base_counts, "semantics": 0, "events": 0, "institutional_actions": 0,
        "risk_windows": 0, "risk_arguments": 0, "influence_pairs": 0,
    }
    interaction_ids = {
        row["interaction_id"] for run in trace["timestamps"] for step in run["steps"]
        for row in step["interactions"]
    }
    revision_ids = {
        row["revision_id"] for run in trace["timestamps"] for step in run["steps"]
        for row in step["belief_revisions"]
    }
    for run in trace["timestamps"]:
        for step in run["steps"]:
            semantics = step["argumentation_semantics"]
            counts["semantics"] += 1
            if set(semantics["input_argument_ids"]) - argument_ids:
                errors.append(f"{run['timestamp']}:k{step['deliberation_step']} semantics có argument lạ")
            if set(semantics["input_relation_ids"]) - relation_ids:
                errors.append(f"{run['timestamp']}:k{step['deliberation_step']} semantics có relation lạ")
            for result in semantics["results"].values():
                if result["semantic_status"] not in {"accepted", "rejected", "undecided"}:
                    errors.append(f"Semantic status không hợp lệ: {result['semantic_status']}")
            for audit in step["institutional_protocol_audit"]:
                counts["institutional_actions"] += 1
                if not audit["valid"]:
                    errors.append(f"Institutional action vi phạm: {audit['action_id']}")
            for event in step["society_events"]:
                counts["events"] += 1
                if event["event_id"] in event_ids:
                    errors.append(f"Society event ID trùng: {event['event_id']}")
                event_ids.add(event["event_id"])
                if set(event["involved_agents"]) - agent_ids:
                    errors.append(f"{event['event_id']} có agent không thuộc runtime base")
                if set(event["involved_arguments"]) - argument_ids:
                    errors.append(f"{event['event_id']} có argument lạ")
                provenance = event["provenance"]
                if set(provenance.get("argument_ids", [])) - argument_ids:
                    errors.append(f"{event['event_id']} có provenance argument lạ")
                if set(provenance.get("relation_ids", [])) - relation_ids:
                    errors.append(f"{event['event_id']} có provenance relation lạ")
                if set(provenance.get("source_ids", [])) - source_ids:
                    errors.append(f"{event['event_id']} có provenance source lạ")
                if not event["explanation"] or not event["threshold"]:
                    errors.append(f"{event['event_id']} thiếu explanation/threshold")
            metrics = step["society_metrics_v3"]
            if metrics["simulation_convergence"] and not metrics["convergence_consensus_separated"]:
                errors.append("Simulation convergence bị đồng nhất với consensus")
            if step["runtime_society_structure"]["base_mapping_immutable"] is not True:
                errors.append("Runtime society không đánh dấu base mapping bất biến")
    argument_types = {row["final_arg_id"]: row["arg_type"] for row in data["selected"]}
    risk_monitoring = trace.get("risk_monitoring")
    if not risk_monitoring:
        errors.append("Trace thiếu risk_monitoring")
    else:
        for window_id, window in risk_monitoring["by_window"].items():
            counts["risk_windows"] += 1
            start_index = window["start_index"]
            end_index = window["end_index"]
            expected_window_id = f"{window['start_snapshot']}__{window['end_snapshot']}"
            if start_index > end_index or window_id != expected_window_id:
                errors.append(f"{window_id}: biên snapshot không hợp lệ")
            rows = window["ranked_arguments"]
            expected = sorted(rows, key=lambda row: (-row["risk_score"], row["argument_id"]))
            if rows != expected:
                errors.append(f"{window_id}: ranking không xác định")
            for row in rows:
                counts["risk_arguments"] += 1
                if argument_types.get(row["argument_id"]) != "A_D":
                    errors.append(f"{window_id}: ranking chứa argument không phải A_D")
                if not all(0.0 <= row[field] <= 1.0 for field in ("conflict_score", "steering_score", "risk_score")):
                    errors.append(f"{window_id}:{row['argument_id']} có score ngoài [0,1]")
                conflict = row["conflict_evidence"]
                for pair in conflict["pairwise_conflicts"]:
                    if set(pair["relation_ids"]) - relation_ids or set(pair["source_ids"]) - source_ids:
                        errors.append(f"{window_id}:{row['argument_id']} conflict provenance lạ")
                for pair in row["steering_evidence"]["pairwise_influence"]:
                    counts["influence_pairs"] += 1
                    if set(pair["relation_ids"]) - relation_ids:
                        errors.append(f"{window_id}:{row['argument_id']} influence relation lạ")
                    if set(pair["interaction_ids"]) - interaction_ids:
                        errors.append(f"{window_id}:{row['argument_id']} influence interaction lạ")
                    if set(pair["revision_ids"]) - revision_ids:
                        errors.append(f"{window_id}:{row['argument_id']} influence revision lạ")
    if errors:
        raise ValueError("V3 trace không hợp lệ:\n- " + "\n- ".join(errors))
    return counts
