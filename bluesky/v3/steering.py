from __future__ import annotations

import re
from datetime import date
from typing import Any

from bluesky.v2.models import rounded

from .config_v3 import SteeringConfig
from .explanation_v3 import steering_explanation


TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _overlaps(start: str, end: str, lower: date, upper: date) -> bool:
    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None
    return (start_date is None or start_date <= upper) and (end_date is None or end_date >= lower)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(value) if len(token) > 1}


class SteeringEvaluator:
    """Deterministic T*L*P influence and normalized outgoing steering baseline."""

    def __init__(
        self,
        data: dict[str, Any],
        snapshots: list[dict[str, Any]],
        trace: dict[str, Any],
        config: SteeringConfig,
    ) -> None:
        self.data = data
        self.snapshots = snapshots
        self.trace = trace
        self.config = config
        self.rank = {row["timestamp_id"]: index for index, row in enumerate(data["timeline"])}
        self.selected = {row["final_arg_id"]: row for row in data["selected"]}
        self.canonical = {row["arg_id"]: row for row in data["canonical"]}
        self.owner = trace["argument_owner"]

    def eligible_discourse(self, start_index: int, end_index: int) -> list[str]:
        return sorted(
            argument_id for argument_id, row in self.selected.items()
            if row["arg_type"] == "A_D"
            and start_index <= self.rank[row["introduced_at"]] <= end_index
        )

    def _window_trace(self, start_index: int, end_index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        interactions: list[dict[str, Any]] = []
        revisions: list[dict[str, Any]] = []
        for index in range(start_index, end_index + 1):
            for step in self.trace["timestamps"][index]["steps"]:
                interactions.extend(step["interactions"])
                revisions.extend(step["belief_revisions"])
        return interactions, revisions

    def pairwise(self, source_id: str, target_id: str, start_index: int, end_index: int) -> dict[str, Any]:
        lower = date.fromisoformat(self.data["timeline"][start_index]["date_start"])
        upper = date.fromisoformat(self.data["timeline"][end_index]["date_end"])
        source_rank = self.rank[self.selected[source_id]["introduced_at"]]
        target_rank = self.rank[self.selected[target_id]["introduced_at"]]
        temporal = 1.0 if source_rank < target_rank else 0.0
        direct = sorted(
            (
                row for row in self.data["relations"]
                if row["source_arg"] == source_id and row["target_arg"] == target_id
                and self.rank[row["introduced_at"]] <= end_index
                and _overlaps(row["valid_from"], row["valid_to"], lower, upper)
            ),
            key=lambda row: row["relation_id"],
        )
        reverse = sorted(
            (
                row for row in self.data["relations"]
                if row["source_arg"] == target_id and row["target_arg"] == source_id
                and self.rank[row["introduced_at"]] <= end_index
                and _overlaps(row["valid_from"], row["valid_to"], lower, upper)
            ),
            key=lambda row: row["relation_id"],
        )
        interactions, revisions = self._window_trace(start_index, end_index)
        target_owner = self.owner[target_id]
        linked_interactions = sorted(
            (
                row for row in interactions
                if row.get("source_argument_id") == source_id
                and (
                    row.get("target_argument_id") == target_id
                    or row.get("target_agent") == target_owner
                )
            ),
            key=lambda row: row["interaction_id"],
        )
        action_ids = {row["action_id"] for row in linked_interactions}
        linked_revisions = sorted(
            (
                row for row in revisions
                if row["argument_id"] == target_id
                and action_ids.intersection(row["trigger_action_ids"])
            ),
            key=lambda row: row["revision_id"],
        )
        components = {
            "direct_relation": 1.0 if direct else 0.0,
            "reverse_response_relation": 1.0 if reverse else 0.0,
            "interaction_reaches_target_owner": 1.0 if linked_interactions else 0.0,
            "linked_belief_revision": 1.0 if linked_revisions else 0.0,
            "explicit_reference_or_exposure": 0.0,
        }
        linkage = rounded(min(1.0, sum(
            components[name] * weight for name, weight in self.config.linkage_weights.items()
        )))
        source_tokens = _tokens(self.canonical[source_id]["conclusion"])
        target_tokens = _tokens(self.canonical[target_id]["conclusion"])
        matched = sorted(source_tokens & target_tokens)
        union = source_tokens | target_tokens
        lexical = len(matched) / len(union) if union else 0.0
        grounded_relation = bool(direct or reverse)
        semantic = max(
            lexical,
            self.config.canonical_relation_semantic_floor if grounded_relation else 0.0,
        )
        semantic = rounded(semantic)
        influence = rounded(temporal * linkage * semantic)
        explicit_response = components["explicit_reference_or_exposure"] > 0 and bool(linked_revisions)
        if influence == 0 or linkage == 0:
            level = "NONE"
        elif explicit_response and linkage >= self.config.strong_evidence_threshold:
            level = "STRONG"
        elif grounded_relation or linked_interactions or linkage >= self.config.medium_evidence_threshold:
            level = "MEDIUM"
        else:
            level = "WEAK"
        relation_ids = sorted({row["relation_id"] for row in direct + reverse})
        return {
            "source_argument_id": source_id,
            "target_argument_id": target_id,
            "T": temporal,
            "L": linkage,
            "P": semantic,
            "I": influence,
            "linkage_evidence_proxy": {
                "components": components,
                "weights": self.config.linkage_weights,
                "score": linkage,
                "limitation": "Liên kết cấu trúc quan sát được; không phải bằng chứng về tiếp xúc hay quan hệ nhân quả.",
            },
            "semantic_position_proxy": {
                "method": self.config.semantic_method,
                "score": semantic,
                "canonical_relation_floor_applied": grounded_relation,
                "lexical_jaccard": rounded(lexical),
                "matched_tokens": matched,
                "limitation": "Liên kết chính tắc hoặc độ trùng từ vựng chỉ là chỉ báo phù hợp tất định.",
            },
            "relation_ids": relation_ids,
            "interaction_ids": [row["interaction_id"] for row in linked_interactions],
            "revision_ids": [row["revision_id"] for row in linked_revisions],
            "evidence_level": level,
            "explanation": (
                f"{source_id} {'xuất hiện trước' if temporal else 'không xuất hiện trước'} {target_id}; "
                f"I={temporal:.1f}×{linkage:.4f}×{semantic:.4f}={influence:.4f}. "
                "Đây là liên hệ cấu trúc, không phải khẳng định nhân quả."
            ),
        }

    def evaluate(self, source_id: str, start_index: int, end_index: int) -> dict[str, Any]:
        eligible = self.eligible_discourse(start_index, end_index)
        pairs = [
            self.pairwise(source_id, target_id, start_index, end_index)
            for target_id in eligible if target_id != source_id
        ]
        denominator = max(1, len(eligible) - 1)
        steering = rounded(sum(row["I"] for row in pairs) / denominator)
        positive = [row for row in pairs if row["I"] > 0]
        interaction_ids = sorted({item for row in positive for item in row["interaction_ids"]})
        revision_ids = sorted({item for row in positive for item in row["revision_ids"]})
        affected = sorted({self.owner[row["target_argument_id"]] for row in positive})
        source_rank = self.rank[self.selected[source_id]["introduced_at"]]
        temporal_depth = max(
            (self.rank[self.selected[row["target_argument_id"]]["introduced_at"]] - source_rank for row in positive),
            default=0,
        )
        visible_window_count = end_index - source_rank + 1
        active_count = 0
        for index in range(source_rank, end_index + 1):
            argument = next((row for row in self.snapshots[index]["arguments"] if row["id"] == source_id), None)
            active_count += bool(argument and argument["activity"] == "active")
        persistence = rounded(active_count / max(1, visible_window_count))
        return {
            "argument_id": source_id,
            "steering_score": steering,
            "pairwise_influence": sorted(pairs, key=lambda row: (-row["I"], row["target_argument_id"])),
            "downstream_argument_count": len(positive),
            "affected_viewpoint_count": len(affected),
            "affected_viewpoints": affected,
            "interaction_count": len(interaction_ids),
            "interaction_ids": interaction_ids,
            "belief_revision_count": len(revision_ids),
            "revision_ids": revision_ids,
            "temporal_depth": temporal_depth,
            "persistence": persistence,
            "denominator": denominator,
            "formula": "S(x,H)=sum_{j!=i} I(x,x_j)/max(1,|A_D(H)|-1)",
            "explanation": steering_explanation(source_id, steering, len(positive)),
        }
