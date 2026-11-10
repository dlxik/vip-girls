from __future__ import annotations

from typing import Any


def validate_trace_provenance(
    trace: dict[str, Any], data: dict[str, Any], snapshots: list[dict[str, Any]]
) -> dict[str, int]:
    argument_ids = {row["final_arg_id"] for row in data["selected"]}
    source_ids = {row["source_id"] for row in data["sources"]}
    relation_ids = {row["relation_id"] for row in data["relations"]}
    snapshot_relations = {
        row["timestamp"]["timestamp_id"]: {relation["id"] for relation in row["relations"]}
        for row in snapshots
    }
    errors: list[str] = []
    counts = {"actions": 0, "interactions": 0, "revisions": 0}
    for run in trace["timestamps"]:
        available_relations = snapshot_relations[run["timestamp"]]
        for step in run["steps"]:
            observation_ids = {row["observation_id"] for row in step["observations"].values()}
            actions = [row for rows in step["candidate_actions"].values() for row in rows]
            for action in actions:
                counts["actions"] += 1
                used_arguments = set(action["provenance"]["argument_ids"])
                used_relations = set(action["provenance"]["relation_ids"])
                used_sources = set(action["provenance"]["source_ids"])
                if used_arguments - argument_ids:
                    errors.append(f"{action['action_id']} có argument không canonical")
                if used_relations - relation_ids or used_relations - available_relations:
                    errors.append(f"{action['action_id']} có relation ngoài G_t")
                if used_sources - source_ids:
                    errors.append(f"{action['action_id']} có source không canonical")
                if action["provenance"]["observation_id"] not in observation_ids:
                    errors.append(f"{action['action_id']} thiếu observation provenance")
            for interaction in step["interactions"]:
                counts["interactions"] += 1
                if set(interaction["relation_ids"]) - available_relations:
                    errors.append(f"{interaction['interaction_id']} có relation ngoài G_t")
                if set(interaction["evidence_source_ids"]) - source_ids:
                    errors.append(f"{interaction['interaction_id']} có source không canonical")
            for revision in step["belief_revisions"]:
                counts["revisions"] += 1
                if revision["argument_id"] not in argument_ids:
                    errors.append(f"{revision['revision_id']} có argument không canonical")
                if set(revision["relation_ids"]) - available_relations:
                    errors.append(f"{revision['revision_id']} có relation ngoài G_t")
                if set(revision["evidence_source_ids"]) - source_ids:
                    errors.append(f"{revision['revision_id']} có source không canonical")
                if revision["observation_id"] not in observation_ids:
                    errors.append(f"{revision['revision_id']} thiếu observation provenance")
    if errors:
        raise ValueError("V2 provenance không hợp lệ:\n- " + "\n- ".join(errors))
    return counts
