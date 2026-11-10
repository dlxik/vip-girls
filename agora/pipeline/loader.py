from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


TIMESTAMP_IDS = ["t1", "t2", "t3", "t4", "t5", "t6"]
SOURCE_TYPES = {"official_document", "authority_statement", "news", "social"}
STATUSES = {"accepted", "rejected", "undecided"}
RELATION_TYPES = {"support", "attack"}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_ids(value: str) -> list[str]:
    return [item for item in value.split(";") if item]


def load_ctq_data() -> dict[str, Any]:
    root = repository_root()
    timeline = _read_csv(root / "data/timelines/ctq_timeline.csv")
    selected = _read_csv(root / "data/annotations/ctq_selected_arguments.csv")
    canonical = _read_csv(root / "data/annotations/ctq_arguments.csv")
    statuses = _read_csv(root / "data/annotations/ctq_argument_status.csv")
    relations = _read_csv(root / "data/annotations/ctq_relations.csv")
    sources = _read_csv(root / "data/sources/ctq_sources.csv")
    with (root / "agora/resources/viewpoint_mapping.json").open("r", encoding="utf-8") as handle:
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
    source_ids = {row["source_id"] for row in sources}

    if timestamp_ids != TIMESTAMP_IDS:
        errors.append(f"Timeline phải đúng thứ tự {TIMESTAMP_IDS}, nhận được {timestamp_ids}")
    if len(selected_ids) != 27 or len(set(selected_ids)) != 27:
        errors.append("Bộ selected phải có đúng 27 final_arg_id duy nhất")
    if set(selected_ids) != set(canonical_ids):
        errors.append("ID giữa selected và canonical arguments không khớp")
    if {row["source_type"] for row in sources} - SOURCE_TYPES:
        errors.append("Source có source_type ngoài miền cho phép")

    for row in selected:
        if row["introduced_at"] not in TIMESTAMP_IDS:
            errors.append(f"{row['final_arg_id']} có introduced_at không hợp lệ")
        missing = set(_split_ids(row["source_ids"])) - source_ids
        if missing:
            errors.append(f"{row['final_arg_id']} tham chiếu source thiếu: {sorted(missing)}")

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
        if set(_split_ids(row["grounded_by"])) - source_ids:
            errors.append(f"Status {key} có grounded_by không hợp lệ")

    relation_ids: set[str] = set()
    for row in relations:
        relation_ids.add(row["relation_id"])
        if row["source_arg"] not in selected_ids or row["target_arg"] not in selected_ids:
            errors.append(f"{row['relation_id']} tham chiếu argument không hợp lệ")
        if row["relation_type"] not in RELATION_TYPES:
            errors.append(f"{row['relation_id']} có relation_type không hợp lệ")
        if row["introduced_at"] not in TIMESTAMP_IDS:
            errors.append(f"{row['relation_id']} có introduced_at không hợp lệ")
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
        mapped_ids.extend(viewpoint.get("argument_ids", []))
    if len(mapped_ids) != len(set(mapped_ids)):
        errors.append("Một argument được gán vào nhiều viewpoint")
    if set(mapped_ids) != set(selected_ids):
        errors.append("Viewpoint mapping phải phủ đúng toàn bộ 27 selected arguments")

    if errors:
        raise ValueError("Dữ liệu CTQ không hợp lệ:\n- " + "\n- ".join(errors))
