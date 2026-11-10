from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config_v3 import DynamicsConfig, ViewpointDynamicsConfig
from .models import DominanceRecord, SocietyEventType
from .society_events import make_event


class SocietyDynamicsEngine:
    def __init__(self, dynamics: DynamicsConfig, viewpoints: ViewpointDynamicsConfig) -> None:
        self.config = dynamics
        self.viewpoint_config = viewpoints
        self.previous_dominant: str | None = None
        self.conflict_streak: dict[tuple[str, str], int] = defaultdict(int)
        self.cohesion_streak: dict[str, int] = defaultdict(int)
        self.active_candidates: set[str] = set()
        self.convergence_emitted: set[str] = set()
        self.previous_components: tuple[tuple[str, ...], ...] | None = None
        self.dominance_history: list[DominanceRecord] = []

    @staticmethod
    def _provenance(interactions: list[dict[str, Any]]) -> dict[str, list[str]]:
        return {
            "interaction_ids": [row["interaction_id"] for row in interactions],
            "action_ids": [row["action_id"] for row in interactions],
            "argument_ids": [
                argument_id for row in interactions
                for argument_id in (row.get("source_argument_id"), row.get("target_argument_id"))
                if argument_id
            ],
            "relation_ids": [relation_id for row in interactions for relation_id in row["relation_ids"]],
            "source_ids": [source_id for row in interactions for source_id in row["evidence_source_ids"]],
        }

    def detect(
        self,
        timestamp: str,
        step: int,
        metrics: dict[str, Any],
        interactions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events = []
        index = 0
        provenance = self._provenance(interactions)
        dominant = metrics["dominant_viewpoint"]
        dominant_value = (
            metrics["structural_prevalence"].get(dominant, {}).get("structural_prevalence", 0.0)
            if dominant else 0.0
        )
        self.dominance_history.append(DominanceRecord(
            timestamp, step, dominant, dominant_value,
            "Maximum structural_prevalence; not real public popularity.",
        ))
        if self.previous_dominant and dominant and dominant != self.previous_dominant:
            index += 1
            events.append(make_event(
                index, timestamp, step, SocietyEventType.DOMINANCE_SHIFT.value,
                [self.previous_dominant, dominant], [],
                {"from": self.previous_dominant, "to": dominant, "to_prevalence": dominant_value},
                {"basis": "max_structural_prevalence"},
                f"Structural dominance shifted from {self.previous_dominant} to {dominant}; this is not public popularity.",
                provenance,
            ).to_dict())
        self.previous_dominant = dominant

        attacked_pairs = {
            tuple(sorted((row["actor_agent"], row["target_agent"])))
            for row in interactions
            if row.get("target_agent") and row["action_type"] in {"ATTACK", "CHALLENGE", "CHALLENGE_INVALID_GROUNDING"}
        }
        for pair in sorted(set(self.conflict_streak) | attacked_pairs):
            self.conflict_streak[pair] = self.conflict_streak[pair] + 1 if pair in attacked_pairs else 0
            if self.conflict_streak[pair] == self.config.persistent_conflict_steps:
                relevant = [row for row in interactions if row.get("target_agent") and tuple(sorted((row["actor_agent"], row["target_agent"]))) == pair]
                index += 1
                events.append(make_event(
                    index, timestamp, step, SocietyEventType.PERSISTENT_CONFLICT.value,
                    list(pair), [arg for row in relevant for arg in (row.get("source_argument_id"), row.get("target_argument_id")) if arg],
                    {"consecutive_attack_steps": self.conflict_streak[pair], "conflict_intensity": metrics["conflict_intensity"]},
                    {"persistent_steps": self.config.persistent_conflict_steps, "confidence_gap": self.config.confidence_gap_threshold},
                    f"Repeated attack/challenge persisted for {self.conflict_streak[pair]} consecutive k steps between {pair[0]} and {pair[1]}.",
                    self._provenance(relevant),
                ).to_dict())

        current_candidates: set[str] = set()
        for candidate in metrics["split_candidates"]:
            key = f"split:{candidate['agent_id']}"
            current_candidates.add(key)
            if key not in self.active_candidates:
                index += 1
                events.append(make_event(
                    index, timestamp, step, SocietyEventType.VIEWPOINT_SPLIT_CANDIDATE.value,
                    [candidate["agent_id"]], candidate["argument_ids"],
                    {"split_score": candidate["score"], **candidate["criteria"]},
                    {"split_score": candidate["threshold"]},
                    "Internal status/confidence/conclusion structure crossed the transparent split-candidate threshold.",
                    provenance,
                ).to_dict())
        for candidate in metrics["merge_candidates"]:
            key = "merge:" + ":".join(candidate["agents"])
            current_candidates.add(key)
            if key not in self.active_candidates:
                index += 1
                event_provenance = dict(provenance)
                event_provenance["relation_ids"] = candidate["relation_ids"]
                events.append(make_event(
                    index, timestamp, step, SocietyEventType.VIEWPOINT_MERGE_CANDIDATE.value,
                    candidate["agents"], candidate["argument_ids"],
                    {"merge_score": candidate["score"], **candidate["criteria"]},
                    {"merge_score": candidate["threshold"]},
                    "Cross-support and similar modeled positions crossed the merge-candidate threshold.",
                    event_provenance,
                ).to_dict())
        self.active_candidates = current_candidates

        for agent_id, row in metrics["viewpoint_cohesion"].items():
            self.cohesion_streak[agent_id] = self.cohesion_streak[agent_id] + 1 if row["cohesion"] >= self.viewpoint_config.stabilization_threshold else 0
            if self.cohesion_streak[agent_id] == self.viewpoint_config.persistent_steps:
                index += 1
                events.append(make_event(
                    index, timestamp, step, SocietyEventType.STABILIZATION.value,
                    [agent_id], [], {"cohesion": row["cohesion"], "steps": self.cohesion_streak[agent_id]},
                    {"cohesion": self.viewpoint_config.stabilization_threshold, "persistent_steps": self.viewpoint_config.persistent_steps},
                    f"{agent_id} maintained high structural cohesion across consecutive k steps.", provenance,
                ).to_dict())

        component_signature = tuple(tuple(row) for row in metrics["weakly_connected_components"])
        if (
            metrics["fragmentation_proxy"] >= self.config.fragmentation_threshold
            and component_signature != self.previous_components
        ):
            index += 1
            events.append(make_event(
                index, timestamp, step, SocietyEventType.FRAGMENTATION_PROXY.value,
                [agent for component in component_signature for agent in component], [],
                {"fragmentation_proxy": metrics["fragmentation_proxy"], "components": metrics["weakly_connected_components"], "isolated": metrics["isolated_agents"]},
                {"fragmentation_proxy": self.config.fragmentation_threshold},
                "Weak-component structure indicates fragmentation inside the simulated interaction graph.",
                provenance,
            ).to_dict())
        self.previous_components = component_signature

        if metrics["convergence_proxy"] >= self.config.consensus_threshold and timestamp not in self.convergence_emitted:
            self.convergence_emitted.add(timestamp)
            index += 1
            events.append(make_event(
                index, timestamp, step, SocietyEventType.CONVERGENCE_PROXY.value,
                sorted(metrics["structural_prevalence"]), [],
                {"convergence_proxy": metrics["convergence_proxy"], "consensus_proxy": metrics["consensus_proxy"], "simulation_convergence": metrics["simulation_convergence"]},
                {"convergence_proxy": self.config.consensus_threshold},
                "Structural convergence proxy crossed threshold; it is explicitly distinct from simulation stop and social consensus.",
                provenance,
            ).to_dict())
        return events

    def history(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.dominance_history]
