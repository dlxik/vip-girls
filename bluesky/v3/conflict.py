from __future__ import annotations

from datetime import date
from typing import Any

from bluesky.v2.models import rounded

from .config_v3 import ConflictConfig
from .explanation_v3 import conflict_explanation


def _split(value: str) -> list[str]:
    return [item for item in value.split(";") if item]


def _overlaps(start: str, end: str, lower: date, upper: date) -> bool:
    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None
    return (start_date is None or start_date <= upper) and (end_date is None or end_date >= lower)


class ConflictEvaluator:
    """Grounded implementation of C(x,H)=max_k Attack*confidence*validity*authority."""

    def __init__(self, data: dict[str, Any], snapshots: list[dict[str, Any]], config: ConflictConfig) -> None:
        self.data = data
        self.snapshots = snapshots
        self.config = config
        self.timeline_rank = {
            row["timestamp_id"]: index for index, row in enumerate(data["timeline"])
        }
        self.selected = {row["final_arg_id"]: row for row in data["selected"]}
        self.canonical = {row["arg_id"]: row for row in data["canonical"]}
        self.sources = {row["source_id"]: row for row in data["sources"]}

    def _authority(self, reference_id: str) -> tuple[float, list[dict[str, Any]]]:
        evidence = []
        for source_id in _split(self.selected[reference_id]["source_ids"]):
            source = self.sources[source_id]
            authority = self.config.authority_weights.get(source["source_type"], 0.0)
            verification = self.config.verification_weights.get(source["verification_status"], 0.0)
            evidence.append({
                "source_id": source_id,
                "source_type": source["source_type"],
                "verification_status": source["verification_status"],
                "authority_weight": authority,
                "verification_weight": verification,
                "combined_quality": rounded(authority * verification),
            })
        return max((row["combined_quality"] for row in evidence), default=0.0), evidence

    def _validity(self, reference_id: str, start_index: int, end_index: int) -> tuple[float, dict[str, Any]]:
        lower = date.fromisoformat(self.data["timeline"][start_index]["date_start"])
        upper = date.fromisoformat(self.data["timeline"][end_index]["date_end"])
        canonical = self.canonical[reference_id]
        temporal_overlap = _overlaps(canonical["valid_from"], canonical["valid_to"], lower, upper)
        endpoint = next(
            (row for row in self.snapshots[end_index]["arguments"] if row["id"] == reference_id),
            None,
        )
        status = endpoint["status"] if endpoint else None
        activity = endpoint["activity"] if endpoint else None
        status_weight = self.config.status_validity.get(status or "", 0.0)
        activity_multiplier = 1.0 if activity == "active" else self.config.historical_multiplier
        score = status_weight * activity_multiplier if temporal_overlap and endpoint else 0.0
        return rounded(score), {
            "temporal_overlap": temporal_overlap,
            "endpoint_timestamp": self.data["timeline"][end_index]["timestamp_id"],
            "status": status,
            "status_weight": status_weight,
            "activity": activity,
            "activity_multiplier": activity_multiplier,
            "rule": "temporal overlap × endpoint status validity × active/historical multiplier",
        }

    def evaluate(self, public_id: str, start_index: int, end_index: int) -> dict[str, Any]:
        lower = date.fromisoformat(self.data["timeline"][start_index]["date_start"])
        upper = date.fromisoformat(self.data["timeline"][end_index]["date_end"])
        eligible_references = sorted(
            argument_id for argument_id, row in self.selected.items()
            if row["arg_type"] == "A_K"
            and self.timeline_rank[row["introduced_at"]] <= end_index
            and _overlaps(
                self.canonical[argument_id]["valid_from"],
                self.canonical[argument_id]["valid_to"], lower, upper,
            )
        )
        pairs = []
        for reference_id in eligible_references:
            relations = sorted(
                (
                    row for row in self.data["relations"]
                    if row["source_arg"] == public_id
                    and row["target_arg"] == reference_id
                    and row["relation_type"] == "attack"
                    and self.timeline_rank[row["introduced_at"]] <= end_index
                    and _overlaps(row["valid_from"], row["valid_to"], lower, upper)
                ),
                key=lambda row: row["relation_id"],
            )
            attack = 1.0 if relations else 0.0
            confidence = max(
                (self.config.relation_confidence.get(row["confidence"], 0.0) for row in relations),
                default=0.0,
            )
            validity, validity_detail = self._validity(reference_id, start_index, end_index)
            authority, authority_detail = self._authority(reference_id)
            score = rounded(attack * confidence * validity * authority)
            relation_ids = [row["relation_id"] for row in relations]
            source_ids = sorted({
                source_id for row in relations for source_id in _split(row["evidence_sources"])
            } | {row["source_id"] for row in authority_detail})
            pairs.append({
                "public_argument_id": public_id,
                "reference_argument_id": reference_id,
                "score": score,
                "attack": attack,
                "relation_confidence": rounded(confidence),
                "validity": validity,
                "validity_detail": validity_detail,
                "authority": authority,
                "authority_detail": authority_detail,
                "relation_ids": relation_ids,
                "source_ids": source_ids,
                "explanation": (
                    f"c={attack:.1f}×{confidence:.4f}×{validity:.4f}×{authority:.4f}={score:.4f}; "
                    "chỉ tính quan hệ tấn công có hướng đã được ghi nhận chính tắc."
                ),
            })
        ranked = sorted(pairs, key=lambda row: (-row["score"], row["reference_argument_id"]))
        maximum = ranked[0] if ranked and ranked[0]["score"] > 0 else None
        score = maximum["score"] if maximum else 0.0
        relation_ids = maximum["relation_ids"] if maximum else []
        reference_id = maximum["reference_argument_id"] if maximum else None
        return {
            "public_argument_id": public_id,
            "conflict_score": score,
            "maximizing_reference_argument_id": reference_id,
            "maximizing_pair": maximum,
            "pairwise_conflicts": ranked,
            "eligible_reference_count": len(eligible_references),
            "formula": "C(x,H)=max_k Attack(x,k,H)*RelationConfidence(x,k)*Validity(k,H)*Authority(k)",
            "explanation": conflict_explanation(public_id, reference_id, score, relation_ids),
        }
