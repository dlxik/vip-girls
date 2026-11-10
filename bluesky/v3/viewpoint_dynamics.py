from __future__ import annotations

import re
from copy import deepcopy
from itertools import combinations
from statistics import mean, pstdev
from typing import Any

from bluesky.v2.models import rounded

from .config_v3 import ViewpointDynamicsConfig
from .models import RuntimeViewpoint


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", text.lower(), flags=re.UNICODE) if len(token) > 2}


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 1.0


class RuntimeSocietyStructure:
    """Runtime overlay. The canonical/base mapping is deep-copied and never mutated."""

    def __init__(self, base_mapping: dict[str, Any]) -> None:
        self.base_viewpoint_mapping = deepcopy(base_mapping)
        self.runtime_viewpoints: dict[str, RuntimeViewpoint] = {
            row["viewpoint_id"]: RuntimeViewpoint(
                runtime_id=row["viewpoint_id"],
                kind="base",
                parent_viewpoints=[row["viewpoint_id"]],
                argument_ids=list(row["argument_ids"]),
                created_at="base",
                created_step=0,
                trigger_event_id=None,
                provenance={"base_mapping": True},
            )
            for row in base_mapping["viewpoints"]
        }

    def register_split(
        self, parent: str, groups: list[list[str]], timestamp: str, step: int, trigger: str
    ) -> list[str]:
        created: list[str] = []
        for index, arguments in enumerate(groups):
            runtime_id = f"{parent}-{chr(65 + index)}"
            self.runtime_viewpoints[runtime_id] = RuntimeViewpoint(
                runtime_id=runtime_id,
                kind="derived_split",
                parent_viewpoints=[parent],
                argument_ids=sorted(arguments),
                created_at=timestamp,
                created_step=step,
                trigger_event_id=trigger,
                provenance={"parent_viewpoint": parent, "contributing_arguments": sorted(arguments)},
            )
            created.append(runtime_id)
        return created

    def register_merge(
        self, parents: list[str], arguments: list[str], timestamp: str, step: int, trigger: str
    ) -> str:
        runtime_id = f"MERGE({','.join(sorted(parents))})"
        self.runtime_viewpoints[runtime_id] = RuntimeViewpoint(
            runtime_id=runtime_id,
            kind="derived_merge",
            parent_viewpoints=sorted(parents),
            argument_ids=sorted(set(arguments)),
            created_at=timestamp,
            created_step=step,
            trigger_event_id=trigger,
            provenance={"parent_viewpoints": sorted(parents), "contributing_arguments": sorted(set(arguments))},
        )
        return runtime_id

    def snapshot(self) -> dict[str, Any]:
        return {
            "base_mapping_immutable": True,
            "runtime_viewpoints": {
                key: value.to_dict() for key, value in sorted(self.runtime_viewpoints.items())
            },
        }


class ViewpointDynamics:
    def __init__(self, config: ViewpointDynamicsConfig, argument_catalog: dict[str, Any]) -> None:
        self.config = config
        self.argument_catalog = argument_catalog

    def _cohesion(
        self,
        agent_id: str,
        state: dict[str, Any],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        beliefs = list(state["belief_states"].values())
        argument_ids = {row["argument_id"] for row in beliefs}
        n = len(beliefs)
        statuses = [row["agent_belief_status"] for row in beliefs]
        status_agreement = max((statuses.count(status) for status in set(statuses)), default=0) / n if n else 0.0
        confidences = [row["confidence"] for row in beliefs]
        dispersion = pstdev(confidences) if len(confidences) > 1 else 0.0
        dispersion_norm = min(1.0, dispersion / 0.5)
        internal = [
            row for row in relations
            if row["source"] in argument_ids and row["target"] in argument_ids
        ]
        possible = n * (n - 1)
        support_density = (
            sum(row["relation_type"] == "support" for row in internal) / possible
            if possible else 1.0
        )
        attack_density = (
            sum(row["relation_type"] == "attack" for row in internal) / possible
            if possible else 0.0
        )
        conclusions = [self.argument_catalog[arg_id]["conclusion"] for arg_id in sorted(argument_ids)]
        similarities = [_jaccard(a, b) for a, b in combinations(conclusions, 2)]
        conclusion_similarity = mean(similarities) if similarities else 1.0
        cohesion = (
            0.35 * status_agreement
            + 0.20 * conclusion_similarity
            + 0.20 * min(1.0, support_density)
            + 0.15 * (1.0 - min(1.0, attack_density))
            + 0.10 * (1.0 - dispersion_norm)
        )
        relation_total = len(internal)
        internal_attack_ratio = (
            sum(row["relation_type"] == "attack" for row in internal) / relation_total
            if relation_total else 0.0
        )
        split_score = (
            0.35 * (1.0 - status_agreement)
            + 0.25 * internal_attack_ratio
            + 0.25 * dispersion_norm
            + 0.15 * (1.0 - conclusion_similarity)
        )
        return {
            "agent_id": agent_id,
            "argument_count": n,
            "cohesion": rounded(cohesion),
            "status_agreement": rounded(status_agreement),
            "conclusion_similarity": rounded(conclusion_similarity),
            "internal_support_density": rounded(support_density),
            "internal_attack_density": rounded(attack_density),
            "internal_conflict": rounded(internal_attack_ratio),
            "confidence_dispersion": rounded(dispersion),
            "split_score": rounded(split_score),
            "formula": "0.35 status agreement + 0.20 conclusion Jaccard + 0.20 support density + 0.15 (1-attack density) + 0.10 confidence consistency",
            "limitation": "Structural cohesion over modeled beliefs; not measured group cohesion.",
        }

    @staticmethod
    def _position(state: dict[str, Any]) -> tuple[float, float]:
        beliefs = list(state["belief_states"].values())
        if not beliefs:
            return 0.0, 0.0
        accepted = sum(row["agent_belief_status"] == "accepted" for row in beliefs) / len(beliefs)
        confidence = mean(row["confidence"] for row in beliefs)
        return accepted, confidence

    def compute(
        self,
        agent_states: dict[str, dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        active = {
            agent_id: state for agent_id, state in agent_states.items()
            if state["belief_states"]
        }
        cohesion = {
            agent_id: self._cohesion(agent_id, state, relations)
            for agent_id, state in sorted(active.items())
        }
        split_candidates = [
            {
                "agent_id": agent_id,
                "score": row["split_score"],
                "threshold": self.config.split_candidate_threshold,
                "argument_ids": sorted(active[agent_id]["belief_states"]),
                "criteria": {
                    "status_agreement": row["status_agreement"],
                    "internal_conflict": row["internal_conflict"],
                    "confidence_dispersion": row["confidence_dispersion"],
                    "conclusion_similarity": row["conclusion_similarity"],
                },
            }
            for agent_id, row in cohesion.items()
            if row["argument_count"] >= 2 and row["split_score"] >= self.config.split_candidate_threshold
        ]
        merge_candidates: list[dict[str, Any]] = []
        for left, right in combinations(sorted(active), 2):
            left_ids = set(active[left]["belief_states"])
            right_ids = set(active[right]["belief_states"])
            cross = [
                row for row in relations
                if (row["source"] in left_ids and row["target"] in right_ids)
                or (row["source"] in right_ids and row["target"] in left_ids)
            ]
            cross_support = sum(row["relation_type"] == "support" for row in cross)
            cross_attack = sum(row["relation_type"] == "attack" for row in cross)
            if not cross_support:
                continue
            left_accepted, left_conf = self._position(active[left])
            right_accepted, right_conf = self._position(active[right])
            status_similarity = 1.0 - abs(left_accepted - right_accepted)
            confidence_similarity = 1.0 - abs(left_conf - right_conf)
            cross_total = cross_support + cross_attack
            support_ratio = cross_support / cross_total
            low_conflict = 1.0 - cross_attack / cross_total
            score = rounded(
                0.40 * status_similarity
                + 0.25 * confidence_similarity
                + 0.20 * support_ratio
                + 0.15 * low_conflict
            )
            if score >= self.config.merge_candidate_threshold:
                merge_candidates.append({
                    "agents": [left, right],
                    "score": score,
                    "threshold": self.config.merge_candidate_threshold,
                    "cross_support": cross_support,
                    "cross_attack": cross_attack,
                    "relation_ids": sorted(row["id"] for row in cross),
                    "argument_ids": sorted(left_ids | right_ids),
                    "criteria": {
                        "status_similarity": rounded(status_similarity),
                        "confidence_similarity": rounded(confidence_similarity),
                        "cross_support_ratio": rounded(support_ratio),
                        "low_conflict": rounded(low_conflict),
                    },
                })
        return {
            "cohesion_by_agent": cohesion,
            "split_candidates": split_candidates,
            "merge_candidates": merge_candidates,
            "thresholds": {
                "split": self.config.split_candidate_threshold,
                "merge": self.config.merge_candidate_threshold,
            },
        }
