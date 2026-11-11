from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

TIMESTAMP_IDS = ["t1", "t2", "t3", "t4", "t5", "t6"]
SOURCE_TYPES = {"official_document", "authority_statement", "news", "social"}
STATUSES = {"accepted", "rejected", "undecided"}
RELATION_TYPES = {"support", "attack"}
ARGUMENT_TYPES = {"A_K", "A_D"}
RELATION_CONFIDENCE = {"high", "medium"}
VERIFICATION_STATUSES = {
    "verified", "verified_copy", "partially_verified", "needs_human_review",
}
REFERENCE_VERIFICATION_STATUSES = {"verified", "verified_copy"}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _parse_date(value: str, label: str, errors: list[str]) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} có ngày không hợp lệ: {value}")
        return None


def _validate_interval(
    start_value: str,
    end_value: str,
    label: str,
    errors: list[str],
) -> None:
    start = _parse_date(start_value, f"{label}.valid_from", errors)
    end = _parse_date(end_value, f"{label}.valid_to", errors)
    if start and end and start > end:
        errors.append(f"{label} có valid_from sau valid_to")


def load_ctq_data() -> dict[str, Any]:
    root = repository_root()
    timeline = _read_csv(root / "data/timelines/ctq_timeline.csv")
    selected = _read_csv(root / "data/annotations/ctq_selected_arguments.csv")
    canonical = _read_csv(root / "data/annotations/ctq_arguments.csv")
    statuses = _read_csv(root / "data/annotations/ctq_argument_status.csv")
    relations = _read_csv(root / "data/annotations/ctq_relations.csv")
    sources = _read_csv(root / "data/sources/ctq_sources.csv")
    with (root / "src/resources/viewpoint_mapping.json").open("r", encoding="utf-8") as handle:
        viewpoint_mapping = json.load(handle)

    _validate(timeline, selected, canonical, statuses, relations, sources, viewpoint_mapping)

    return {
        "timeline": timeline,
        "selected": selected,
        "canonical": canonical,
        "statuses": statuses,
        "relations": relations,
        "sources": sources,
        "viewpoint_mapping": viewpoint_mapping,
    }


def _validate(
    timeline: list[dict[str, str]],
    selected: list[dict[str, str]],
    canonical: list[dict[str, str]],
    statuses: list[dict[str, str]],
    relations: list[dict[str, str]],
    sources: list[dict[str, str]],
    viewpoint_mapping: dict[str, Any],
) -> None:
    errors: list[str] = []
    timestamp_ids = [row["timestamp_id"] for row in timeline]
    selected_ids = [row["final_arg_id"] for row in selected]
    canonical_ids = [row["arg_id"] for row in canonical]
    source_id_list = [row["source_id"] for row in sources]
    source_ids = set(source_id_list)
    source_by_id = {row["source_id"]: row for row in sources}
    selected_by_id = {row["final_arg_id"]: row for row in selected}
    canonical_by_id = {row["arg_id"]: row for row in canonical}
    rank = {timestamp_id: index for index, timestamp_id in enumerate(TIMESTAMP_IDS)}

    if timestamp_ids != TIMESTAMP_IDS:
        errors.append(f"Timeline phải đúng thứ tự {TIMESTAMP_IDS}, nhận được {timestamp_ids}")
    if duplicates := _duplicates(timestamp_ids):
        errors.append(f"Timeline có timestamp_id trùng: {duplicates}")
    if len(selected_ids) != 27 or len(set(selected_ids)) != 27:
        errors.append("Bộ selected phải có đúng 27 final_arg_id duy nhất")
    if duplicates := _duplicates(canonical_ids):
        errors.append(f"Canonical argument ID trùng: {duplicates}")
    if set(selected_ids) != set(canonical_ids):
        errors.append("ID giữa selected và canonical arguments không khớp")
    if duplicates := _duplicates(source_id_list):
        errors.append(f"Source ID trùng: {duplicates}")
    if {row["source_type"] for row in sources} - SOURCE_TYPES:
        errors.append("Source có source_type ngoài miền cho phép")
    if {row["verification_status"] for row in sources} - VERIFICATION_STATUSES:
        errors.append("Source có verification_status ngoài miền cho phép")

    previous_end: date | None = None
    for row in timeline:
        start = _parse_date(row["date_start"], f"Timeline {row['timestamp_id']}.date_start", errors)
        end = _parse_date(row["date_end"], f"Timeline {row['timestamp_id']}.date_end", errors)
        if start and end and start > end:
            errors.append(f"Timeline {row['timestamp_id']} có date_start sau date_end")
        if previous_end and start and start <= previous_end:
            errors.append(f"Timeline {row['timestamp_id']} chồng lấn hoặc không tăng")
        if end:
            previous_end = end

    for row in selected:
        if row["introduced_at"] not in TIMESTAMP_IDS:
            errors.append(f"{row['final_arg_id']} có introduced_at không hợp lệ")
        if row["arg_type"] not in ARGUMENT_TYPES:
            errors.append(f"{row['final_arg_id']} có arg_type không hợp lệ")
        missing = set(_split_ids(row["source_ids"])) - source_ids
        if missing:
            errors.append(f"{row['final_arg_id']} tham chiếu source thiếu: {sorted(missing)}")

    for row in canonical:
        argument_id = row["arg_id"]
        _validate_interval(row["valid_from"], row["valid_to"], argument_id, errors)
        introduced_at = selected_by_id.get(argument_id, {}).get("introduced_at")
        active_until = row["active_until"] or "t6"
        if active_until not in TIMESTAMP_IDS:
            errors.append(f"{argument_id} có active_until không hợp lệ")
        elif introduced_at in rank and rank[active_until] < rank[introduced_at]:
            errors.append(f"{argument_id} có active_until trước introduced_at")

    status_keys: set[tuple[str, str]] = set()
    for row in statuses:
        key = (row["arg_id"], row["timestamp_id"])
        if key in status_keys:
            errors.append(f"Status trùng khóa: {key}")
        status_keys.add(key)
        if row["arg_id"] not in selected_ids or row["timestamp_id"] not in TIMESTAMP_IDS:
            errors.append(f"Status tham chiếu ID không hợp lệ: {key}")
        if row["status"] not in STATUSES:
            errors.append(f"Status không hợp lệ: {row['status']}")
        grounding_ids = _split_ids(row["grounded_by"])
        if set(grounding_ids) - source_ids:
            errors.append(f"Status {key} có grounded_by không hợp lệ")
        selected_row = selected_by_id.get(row["arg_id"])
        if (
            selected_row
            and selected_row["arg_type"] == "A_K"
            and row["status"] == "accepted"
        ):
            has_reference = any(
                source_by_id.get(source_id, {}).get("source_type") == "official_document"
                and source_by_id[source_id].get("verification_status")
                in REFERENCE_VERIFICATION_STATUSES
                for source_id in grounding_ids
            )
            if not has_reference:
                errors.append(
                    f"Status {key} accepted A_K thiếu official_document đã xác minh"
                )

    for argument_id in selected_ids:
        selected_row = selected_by_id.get(argument_id)
        canonical_row = canonical_by_id.get(argument_id)
        if not selected_row or not canonical_row:
            continue
        start_id = selected_row["introduced_at"]
        end_id = canonical_row["active_until"] or "t6"
        if start_id not in rank or end_id not in rank:
            continue
        required = {
            (argument_id, timestamp_id)
            for timestamp_id in TIMESTAMP_IDS[rank[start_id] : rank[end_id] + 1]
        }
        missing_statuses = required - status_keys
        if missing_statuses:
            errors.append(
                f"{argument_id} thiếu status active tại: "
                f"{sorted(timestamp_id for _, timestamp_id in missing_statuses)}"
            )

    relation_ids: set[str] = set()
    for row in relations:
        if row["relation_id"] in relation_ids:
            errors.append(f"Relation ID trùng: {row['relation_id']}")
        relation_ids.add(row["relation_id"])
        if row["source_arg"] not in selected_ids or row["target_arg"] not in selected_ids:
            errors.append(f"{row['relation_id']} tham chiếu argument không hợp lệ")
        if row["source_arg"] == row["target_arg"]:
            errors.append(f"{row['relation_id']} không được tự trỏ")
        if row["relation_type"] not in RELATION_TYPES:
            errors.append(f"{row['relation_id']} có relation_type không hợp lệ")
        if row["confidence"] not in RELATION_CONFIDENCE:
            errors.append(f"{row['relation_id']} có confidence không hợp lệ")
        if row["introduced_at"] not in TIMESTAMP_IDS:
            errors.append(f"{row['relation_id']} có introduced_at không hợp lệ")
        _validate_interval(
            row["valid_from"], row["valid_to"], row["relation_id"], errors
        )
        if not row["evidence_sources"]:
            errors.append(f"{row['relation_id']} thiếu evidence_sources")
        if set(_split_ids(row["evidence_sources"])) - source_ids:
            errors.append(f"{row['relation_id']} có evidence_sources không hợp lệ")

    mapped_ids: list[str] = []
    for viewpoint in viewpoint_mapping.get("viewpoints", []):
        for field in ("viewpoint_id", "kind", "name", "position_summary", "inclusion_rule", "argument_ids"):
            if not viewpoint.get(field):
                errors.append(f"Viewpoint thiếu trường bắt buộc {field}: {viewpoint.get('viewpoint_id', '?')}")
        if viewpoint.get("kind") not in {"collective", "contextual"}:
            errors.append(f"Viewpoint có kind không hợp lệ: {viewpoint.get('viewpoint_id', '?')}")
        argument_ids = viewpoint.get("argument_ids", [])
        if duplicates := _duplicates(argument_ids):
            errors.append(
                f"Viewpoint {viewpoint.get('viewpoint_id', '?')} lặp argument: {duplicates}"
            )
        mapped_ids.extend(argument_ids)
    if set(mapped_ids) != set(selected_ids):
        errors.append("Viewpoint mapping phải phủ đúng toàn bộ 27 selected arguments")

    if errors:
        raise ValueError("Dữ liệu CTQ không hợp lệ:\n- " + "\n- ".join(errors))
