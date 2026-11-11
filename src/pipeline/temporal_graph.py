from __future__ import annotations

from datetime import date
from typing import Any

from .loader import TIMESTAMP_IDS


def _split_ids(value: str) -> list[str]:
    return [item for item in value.split(";") if item]


def _date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def build_temporal_snapshots(data: dict[str, Any]) -> list[dict[str, Any]]:
    rank = {timestamp_id: index for index, timestamp_id in enumerate(TIMESTAMP_IDS)}
    canonical_by_id = {row["arg_id"]: row for row in data["canonical"]}
    source_by_id = {row["source_id"]: row for row in data["sources"]}
    status_by_key = {
        (row["arg_id"], row["timestamp_id"]): row for row in data["statuses"]
    }
    snapshots: list[dict[str, Any]] = []

    for timestamp in data["timeline"]:
        timestamp_id = timestamp["timestamp_id"]
        timestamp_rank = rank[timestamp_id]
        visible_arguments: list[dict[str, Any]] = []

        for selected in data["selected"]:
            canonical = canonical_by_id[selected["final_arg_id"]]
            introduced_rank = rank[selected["introduced_at"]]
            if introduced_rank > timestamp_rank:
                continue

            argument_id = selected["final_arg_id"]
            status_row = status_by_key.get((argument_id, timestamp_id))
            active_until = canonical["active_until"] or "t6"
            activity = "active" if rank[active_until] >= timestamp_rank else "historical"
            if activity == "active" and status_row is None:
                raise ValueError(f"Thiếu status cho argument active {argument_id} tại {timestamp_id}")

            status_basis = "recorded"
            status_timestamp = timestamp_id
            if status_row is None:
                for previous_id in reversed(TIMESTAMP_IDS[:timestamp_rank]):
                    previous_status = status_by_key.get((argument_id, previous_id))
                    if previous_status:
                        status_row = previous_status
                        status_basis = "carried_forward"
                        status_timestamp = previous_id
                        break
            if status_row is None:
                raise ValueError(f"Không tìm thấy status đã biết cho argument lịch sử {argument_id} tại {timestamp_id}")

            source_ids = _split_ids(selected["source_ids"])
            visible_arguments.append({
                "id": selected["final_arg_id"],
                "candidate_id": selected["candidate_id"],
                "arg_type": selected["arg_type"],
                "premise": canonical["premise"],
                "rule": canonical["rule"] or None,
                "conclusion": canonical["conclusion"],
                "source_ids": source_ids,
                "source_type": selected["source_type"],
                "sources": [
                    {
                        "source_id": source_id,
                        "title": source_by_id[source_id]["title"],
                        "url": source_by_id[source_id]["url"],
                        "source_type": source_by_id[source_id]["source_type"],
                        "publisher": source_by_id[source_id]["publisher"],
                        "verification_status": source_by_id[source_id]["verification_status"],
                    }
                    for source_id in source_ids
                ],
                "introduced_at": selected["introduced_at"],
                "active_until": canonical["active_until"] or None,
                "temporal_role": selected["temporal_role"],
                "status": status_row["status"],
                "semantic_status": status_row["status"],
                "status_reason": status_row["reason"],
                "grounded_by": _split_ids(status_row["grounded_by"]),
                "status_basis": status_basis,
                "status_timestamp": status_timestamp,
                "activity": activity,
                "active": activity == "active",
                "newly_introduced": selected["introduced_at"] == timestamp_id,
            })

        visible_ids = {argument["id"] for argument in visible_arguments}
        start = _date(timestamp["date_start"])
        end = _date(timestamp["date_end"])
        visible_relations: list[dict[str, Any]] = []
        for relation in data["relations"]:
            relation_start = _date(relation["valid_from"])
            relation_end = _date(relation["valid_to"])
            is_introduced = rank[relation["introduced_at"]] <= timestamp_rank
            is_date_valid = (
                (relation_start is None or relation_start <= end)
                and (relation_end is None or relation_end >= start)
            )
            endpoints_visible = (
                relation["source_arg"] in visible_ids and relation["target_arg"] in visible_ids
            )
            if not (is_introduced and is_date_valid and endpoints_visible):
                continue
            visible_relations.append({
                "id": relation["relation_id"],
                "source": relation["source_arg"],
                "target": relation["target_arg"],
                "relation_type": relation["relation_type"],
                "conflict_type": relation["conflict_type"] or None,
                "introduced_at": relation["introduced_at"],
                "valid_from": relation["valid_from"] or None,
                "valid_to": relation["valid_to"] or None,
                "evidence_sources": _split_ids(relation["evidence_sources"]),
                "confidence": relation["confidence"],
                "notes": relation["notes"],
                "newly_introduced": relation["introduced_at"] == timestamp_id,
            })

        for argument in visible_arguments:
            incoming = [relation for relation in visible_relations if relation["target"] == argument["id"]]
            outgoing = [relation for relation in visible_relations if relation["source"] == argument["id"]]
            argument["incoming_support"] = [r["id"] for r in incoming if r["relation_type"] == "support"]
            argument["incoming_attack"] = [r["id"] for r in incoming if r["relation_type"] == "attack"]
            argument["outgoing_support"] = [r["id"] for r in outgoing if r["relation_type"] == "support"]
            argument["outgoing_attack"] = [r["id"] for r in outgoing if r["relation_type"] == "attack"]
            argument["new_incoming_relations"] = [r["id"] for r in incoming if r["newly_introduced"]]

        snapshots.append({
            "timestamp": timestamp,
            "arguments": visible_arguments,
            "relations": visible_relations,
        })

    _add_snapshot_diffs_and_explanations(snapshots)
    return snapshots


def _add_snapshot_diffs_and_explanations(snapshots: list[dict[str, Any]]) -> None:
    previous_arguments: dict[str, dict[str, Any]] = {}
    previous_relations: set[str] = set()

    for index, snapshot in enumerate(snapshots):
        current_arguments = {argument["id"]: argument for argument in snapshot["arguments"]}
        current_relations = {relation["id"]: relation for relation in snapshot["relations"]}
        new_argument_ids = [arg_id for arg_id in current_arguments if arg_id not in previous_arguments]
        changed_statuses = []
        activity_changes = []

        for arg_id, argument in current_arguments.items():
            previous = previous_arguments.get(arg_id)
            if previous and previous["semantic_status"] != argument["semantic_status"]:
                changed_statuses.append({
                    "arg_id": arg_id,
                    "from": previous["semantic_status"],
                    "to": argument["semantic_status"],
                })
            if previous and previous["activity"] != argument["activity"]:
                activity_changes.append({
                    "arg_id": arg_id,
                    "from": previous["activity"],
                    "to": argument["activity"],
                })

        new_relation_ids = [relation_id for relation_id in current_relations if relation_id not in previous_relations]
        new_relations = [current_relations[relation_id] for relation_id in new_relation_ids]
        newly_accepted = [
            arg_id for arg_id, argument in current_arguments.items()
            if argument["semantic_status"] == "accepted"
            and (arg_id not in previous_arguments or previous_arguments[arg_id]["semantic_status"] != "accepted")
        ]
        newly_rejected = [
            arg_id for arg_id, argument in current_arguments.items()
            if argument["semantic_status"] == "rejected"
            and (arg_id not in previous_arguments or previous_arguments[arg_id]["semantic_status"] != "rejected")
        ]

        snapshot["changes"] = {
            "transition": "Khởi tạo t1" if index == 0 else f"{snapshots[index - 1]['timestamp']['timestamp_id']} → {snapshot['timestamp']['timestamp_id']}",
            "new_arguments": new_argument_ids,
            "changed_statuses": changed_statuses,
            "activity_changes": activity_changes,
            "newly_accepted": newly_accepted,
            "newly_rejected": newly_rejected,
            "new_support_relations": [r["id"] for r in new_relations if r["relation_type"] == "support"],
            "new_attack_relations": [r["id"] for r in new_relations if r["relation_type"] == "attack"],
        }

        for argument in snapshot["arguments"]:
            previous = previous_arguments.get(argument["id"])
            status_change = None
            activity_change = None
            if previous and previous["semantic_status"] != argument["semantic_status"]:
                status_change = {"from": previous["semantic_status"], "to": argument["semantic_status"]}
            if previous and previous["activity"] != argument["activity"]:
                activity_change = {"from": previous["activity"], "to": argument["activity"]}

            relevant = [
                current_relations[relation_id]
                for relation_id in argument["new_incoming_relations"]
                if relation_id in current_relations
            ]
            evidence_arguments = []
            evidence_sources = list(argument["grounded_by"])
            interpretations = [argument["status_reason"]]
            for relation in relevant:
                if relation["source"] not in evidence_arguments:
                    evidence_arguments.append(relation["source"])
                for source_id in relation["evidence_sources"]:
                    if source_id not in evidence_sources:
                        evidence_sources.append(source_id)
                if relation["notes"] not in interpretations:
                    interpretations.append(relation["notes"])

            argument["change_explanation"] = {
                "changed": bool(status_change or activity_change or argument["newly_introduced"]),
                "status_change": status_change,
                "activity_change": activity_change,
                "new_evidence_arguments": evidence_arguments,
                "relevant_relation_ids": [relation["id"] for relation in relevant],
                "evidence_sources": evidence_sources,
                "interpretation": interpretations,
            }

        previous_arguments = current_arguments
        previous_relations = set(current_relations)
