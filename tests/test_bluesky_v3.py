from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import replace

from bluesky.src.loader import load_ctq_data
from bluesky.src.temporal_graph import build_temporal_snapshots
from bluesky.src.viewpoint import add_viewpoint_layers
from bluesky.v2.models import AgentAction
from bluesky.v2.simulation import AutonomousArgumentationSimulation
from bluesky.v3.config_v3 import DEFAULT_V3_CONFIG
from bluesky.v3.institutional_policy import InstitutionalActionPolicy
from bluesky.v3.metrics_v3 import SocietyMetricsV3
from bluesky.v3.models import SocietyEventType
from bluesky.v3.prevalence import StructuralPrevalenceCalculator
from bluesky.v3.semantics import WeightedBipolarSemantics
from bluesky.v3.simulation_v3 import DynamicSocietySimulation
from bluesky.v3.society_dynamics import SocietyDynamicsEngine
from bluesky.v3.validation_v3 import validate_v3_trace
from bluesky.v3.visualizer_v3 import HTML as V3_HTML
from bluesky.v3.viewpoint_dynamics import RuntimeSocietyStructure, ViewpointDynamics


class DynamicAgentSocietyV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_ctq_data()
        cls.snapshots = build_temporal_snapshots(cls.data)
        add_viewpoint_layers(cls.snapshots, cls.data["viewpoint_mapping"])
        cls.base_mapping = deepcopy(cls.data["viewpoint_mapping"])
        cls.v2_trace = AutonomousArgumentationSimulation(cls.data, cls.snapshots).run()
        cls.trace = DynamicSocietySimulation(cls.data, cls.snapshots).run()

    def test_v1_temporal_graph_still_runs(self) -> None:
        self.assertEqual(6, len(self.snapshots))
        self.assertEqual("t1", self.snapshots[0]["timestamp"]["timestamp_id"])
        self.assertTrue(self.snapshots[-1]["viewpoints"])

    def test_v2_still_runs_independently(self) -> None:
        self.assertEqual("agora-v2-trace-1.0", self.v2_trace["schema_version"])
        self.assertEqual(6, len(self.v2_trace["timestamps"]))

    def test_v3_initializes_and_keeps_time_semantics(self) -> None:
        self.assertEqual("agora-v3-trace-1.0", self.trace["schema_version"])
        self.assertEqual(6, len(self.trace["timestamps"]))
        self.assertIn("society_event", self.trace["time_semantics"])
        self.assertNotIn("e", self.trace["time_semantics"])

    def test_semantics_is_deterministic_and_explainable(self) -> None:
        scores = {"A": 0.7, "B": 0.4}
        relations = [{
            "id": "R", "source": "A", "target": "B", "relation_type": "support",
            "confidence": "high", "evidence_sources": ["S"],
        }]
        engine = WeightedBipolarSemantics(
            DEFAULT_V3_CONFIG.semantics, {"high": 1.0, "medium": 0.7}
        )
        first = engine.evaluate(scores, relations)
        second = engine.evaluate(scores, relations)
        self.assertEqual(first, second)
        self.assertEqual("weighted_bipolar_fixed_point", first["method"])
        self.assertEqual("R", first["results"]["B"]["incoming_derivation"][0]["relation_id"])

    def test_semantics_explicitly_participates_in_revision(self) -> None:
        step = self.trace["timestamps"][0]["steps"][0]
        for row in step["argumentation_semantics"]["results"].values():
            expected = round(
                (1.0 - DEFAULT_V3_CONFIG.semantic_revision_blend) * row["heuristic_score"]
                + DEFAULT_V3_CONFIG.semantic_revision_blend * row["semantic_score"],
                4,
            )
            self.assertEqual(expected, row["revision_blend_score"])
            self.assertEqual(
                DEFAULT_V3_CONFIG.semantic_revision_blend,
                row["revision_blend_coefficient"],
            )

    def test_cohesion_computation(self) -> None:
        step = self.trace["timestamps"][3]["steps"][0]
        cohesion = step["viewpoint_dynamics"]["cohesion_by_agent"]
        self.assertIn("VP04", cohesion)
        self.assertGreaterEqual(cohesion["VP04"]["cohesion"], 0.0)
        self.assertLessEqual(cohesion["VP04"]["cohesion"], 1.0)
        self.assertIn("formula", cohesion["VP04"])

    def test_prevalence_computation(self) -> None:
        step = self.trace["timestamps"][5]["steps"][-1]
        prevalence = step["structural_prevalence"]
        self.assertIsNone(prevalence["real_social_prevalence"])
        self.assertIn("structural_prevalence", prevalence["by_agent"]["VP06"])
        self.assertIn("not measurements of real public support", prevalence["limitation"])

    def test_split_candidate_detection(self) -> None:
        catalog = {
            "A": {"conclusion": "Biện pháp chỉ giới hạn môn Toán"},
            "B": {"conclusion": "Phải thi lại toàn bộ các môn"},
        }
        dynamics = ViewpointDynamics(DEFAULT_V3_CONFIG.viewpoint_dynamics, catalog)
        states = {"VPX": {"belief_states": {
            "A": {"argument_id": "A", "agent_belief_status": "accepted", "confidence": 0.9},
            "B": {"argument_id": "B", "agent_belief_status": "rejected", "confidence": 0.1},
        }}}
        relations = [{"id": "R", "source": "A", "target": "B", "relation_type": "attack"}]
        result = dynamics.compute(states, relations)
        self.assertEqual("VPX", result["split_candidates"][0]["agent_id"])

    def test_merge_candidate_detection(self) -> None:
        catalog = {"A": {"conclusion": "x"}, "B": {"conclusion": "x"}}
        dynamics = ViewpointDynamics(DEFAULT_V3_CONFIG.viewpoint_dynamics, catalog)
        states = {
            "VPA": {"belief_states": {"A": {"argument_id": "A", "agent_belief_status": "accepted", "confidence": 0.8}}},
            "VPB": {"belief_states": {"B": {"argument_id": "B", "agent_belief_status": "accepted", "confidence": 0.8}}},
        }
        relations = [{"id": "R", "source": "A", "target": "B", "relation_type": "support"}]
        result = dynamics.compute(states, relations)
        self.assertEqual(["VPA", "VPB"], result["merge_candidates"][0]["agents"])

    def test_runtime_split_merge_scaffold_preserves_base_ids(self) -> None:
        structure = RuntimeSocietyStructure(self.data["viewpoint_mapping"])
        base_ids = set(structure.runtime_viewpoints)
        split_ids = structure.register_split("VP04", [["CTQ-A009"], ["CTQ-A011"]], "t4", 1, "SE-X")
        merged = structure.register_merge(["VP01", "VP07"], ["CTQ-A002", "CTQ-A019"], "t5", 1, "SE-Y")
        self.assertEqual(["VP04-A", "VP04-B"], split_ids)
        self.assertEqual("MERGE(VP01,VP07)", merged)
        self.assertTrue(base_ids.issubset(structure.runtime_viewpoints))

    def test_institutional_action_restrictions(self) -> None:
        catalog = self.trace["argument_catalog"]
        policy = InstitutionalActionPolicy(
            self.trace["argument_owner"], self.data["sources"], catalog
        )
        common = dict(
            action_id="A", timestamp="t1", deliberation_step=0, actor_agent="CTX01",
            target_agent="VP01", source_argument_id="CTQ-A001", target_argument_id="CTQ-A002",
            relation_ids=[], evidence_source_ids=["CTQ-S018"], rationale="test", utility=1.0,
            provenance={"argument_ids": [], "relation_ids": [], "source_ids": ["CTQ-S018"], "observation_id": "O"},
        )
        forbidden = AgentAction(action_type="ATTACK", **common)
        allowed = AgentAction(action_type="CLARIFY_AUTHORITY", **common)
        self.assertFalse(policy.validate_restrictions(forbidden)[0])
        self.assertTrue(policy.validate_restrictions(allowed)[0])

    @staticmethod
    def _minimal_metrics(dominant: str, fragmentation: float = 0.0) -> dict:
        return {
            "dominant_viewpoint": dominant,
            "structural_prevalence": {
                "A": {"structural_prevalence": 0.4},
                "B": {"structural_prevalence": 0.6},
            },
            "conflict_intensity": 0.7,
            "split_candidates": [],
            "merge_candidates": [],
            "viewpoint_cohesion": {},
            "fragmentation_proxy": fragmentation,
            "weakly_connected_components": [["A"], ["B"]] if fragmentation else [["A", "B"]],
            "isolated_agents": ["A", "B"] if fragmentation else [],
            "convergence_proxy": 0.0,
            "consensus_proxy": 0.0,
            "simulation_convergence": False,
        }

    def test_dominance_shift_detection(self) -> None:
        engine = SocietyDynamicsEngine(DEFAULT_V3_CONFIG.dynamics, DEFAULT_V3_CONFIG.viewpoint_dynamics)
        engine.detect("t1", 0, self._minimal_metrics("A"), [])
        events = engine.detect("t1", 1, self._minimal_metrics("B"), [])
        self.assertIn(SocietyEventType.DOMINANCE_SHIFT.value, {row["event_type"] for row in events})

    def test_persistent_conflict_detection(self) -> None:
        engine = SocietyDynamicsEngine(DEFAULT_V3_CONFIG.dynamics, DEFAULT_V3_CONFIG.viewpoint_dynamics)
        interaction = {
            "interaction_id": "I", "action_id": "A", "actor_agent": "A", "target_agent": "B",
            "action_type": "ATTACK", "source_argument_id": "X", "target_argument_id": "Y",
            "relation_ids": ["R"], "evidence_source_ids": ["S"],
        }
        engine.detect("t1", 0, self._minimal_metrics("A"), [interaction])
        events = engine.detect("t1", 1, self._minimal_metrics("A"), [interaction])
        self.assertIn(SocietyEventType.PERSISTENT_CONFLICT.value, {row["event_type"] for row in events})

    def test_persistent_conflict_event_order_is_stable(self) -> None:
        engine = SocietyDynamicsEngine(DEFAULT_V3_CONFIG.dynamics, DEFAULT_V3_CONFIG.viewpoint_dynamics)
        interactions = [
            {
                "interaction_id": f"I-{actor}", "action_id": f"ACT-{actor}",
                "actor_agent": actor, "target_agent": target, "action_type": "ATTACK",
                "source_argument_id": "X", "target_argument_id": "Y",
                "relation_ids": ["R"], "evidence_source_ids": ["S"],
            }
            for actor, target in [("B", "C"), ("A", "D")]
        ]
        engine.detect("t1", 0, self._minimal_metrics("A"), interactions)
        events = engine.detect("t1", 1, self._minimal_metrics("A"), interactions)
        conflicts = [row["involved_agents"] for row in events if row["event_type"] == "PERSISTENT_CONFLICT"]
        self.assertEqual([["A", "D"], ["B", "C"]], conflicts)

    def test_fragmentation_detection(self) -> None:
        engine = SocietyDynamicsEngine(DEFAULT_V3_CONFIG.dynamics, DEFAULT_V3_CONFIG.viewpoint_dynamics)
        events = engine.detect("t1", 0, self._minimal_metrics("A", 1.0), [])
        self.assertIn(SocietyEventType.FRAGMENTATION_PROXY.value, {row["event_type"] for row in events})

    def test_convergence_and_consensus_are_separate(self) -> None:
        for run in self.trace["timestamps"]:
            for step in run["steps"]:
                metrics = step["society_metrics_v3"]
                self.assertTrue(metrics["convergence_consensus_separated"])
                self.assertIn("simulation_convergence", metrics)
                self.assertIn("consensus_proxy", metrics)

    def test_runtime_event_provenance_and_validation(self) -> None:
        counts = validate_v3_trace(self.trace, self.data, self.snapshots)
        self.assertGreater(counts["events"], 0)
        for event in self.trace["society_events"]:
            self.assertIn("argument_ids", event["provenance"])
            self.assertIn("relation_ids", event["provenance"])
            self.assertIn("source_ids", event["provenance"])

    def test_no_canonical_mapping_mutation(self) -> None:
        self.assertEqual(self.base_mapping, self.data["viewpoint_mapping"])
        self.assertEqual(self.base_mapping, self.trace["base_viewpoint_mapping"])

    def test_deterministic_replay(self) -> None:
        again = DynamicSocietySimulation(self.data, self.snapshots).run()
        self.assertEqual(
            json.dumps(self.trace, sort_keys=True, ensure_ascii=False),
            json.dumps(again, sort_keys=True, ensure_ascii=False),
        )

    def test_v3_config_does_not_change_v2_output(self) -> None:
        before = AutonomousArgumentationSimulation(self.data, self.snapshots).run()
        config = replace(DEFAULT_V3_CONFIG, semantics=replace(DEFAULT_V3_CONFIG.semantics, damping=0.55))
        DynamicSocietySimulation(self.data, self.snapshots, config).run()
        after = AutonomousArgumentationSimulation(self.data, self.snapshots).run()
        self.assertEqual(before, after)

    def test_personal_and_organization_types_not_instantiated(self) -> None:
        supported = self.trace["supported_agent_types"]
        self.assertIn("not instantiated", supported["personal"])
        self.assertIn("not instantiated", supported["organization"])

    def test_v3_inherits_draggable_node_layout(self) -> None:
        self.assertIn("function initNodeDragging()", V3_HTML)
        self.assertIn("manualPositions:loadLayout()", V3_HTML)
        self.assertIn("resetLayout", V3_HTML)


if __name__ == "__main__":
    unittest.main()
