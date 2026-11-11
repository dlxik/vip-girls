from __future__ import annotations

import hashlib
import unittest

from hierarchy.config import PropagationConfig
from hierarchy.hierarchy import AgentHierarchy
from hierarchy.models import ArgumentSubAgent
from hierarchy.propagation import DeterministicMessageQueue
from hierarchy.simulation import HierarchicalArgumentSocietySimulation
from hierarchy.steering import ArrivalAwareSteeringEvaluator
from hierarchy.validation import validate_hierarchy_trace
from hierarchy.visualizer import HTML
from pipeline.loader import load_ctq_data, repository_root
from pipeline.temporal_graph import build_temporal_snapshots
from pipeline.viewpoint import add_viewpoint_layers
from society.config import DEFAULT_SOCIETY_CONFIG


class HierarchicalArgumentSocietyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_ctq_data()
        cls.snapshots = build_temporal_snapshots(cls.data)
        add_viewpoint_layers(cls.snapshots, cls.data["viewpoint_mapping"])
        root = repository_root()
        cls.canonical_paths = [
            root / "data/annotations/ctq_selected_arguments.csv",
            root / "data/annotations/ctq_arguments.csv",
            root / "data/annotations/ctq_argument_status.csv",
            root / "data/annotations/ctq_relations.csv",
            root / "data/sources/ctq_sources.csv",
            root / "src/resources/viewpoint_mapping.json",
        ]
        cls.hashes_before = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in cls.canonical_paths
        }
        cls.trace = HierarchicalArgumentSocietySimulation(
            cls.data, cls.snapshots
        ).run()

    def test_one_subagent_per_selected_argument_and_canonical_unchanged(self) -> None:
        selected = {row["final_arg_id"] for row in self.data["selected"]}
        subagents = self.trace["argument_subagents"]
        self.assertEqual(27, len(subagents))
        self.assertEqual(selected, {row["argument_id"] for row in subagents.values()})
        self.assertEqual(27, len({row["argument_id"] for row in subagents.values()}))
        self.assertEqual(
            self.hashes_before,
            {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.canonical_paths
            },
        )

    def test_parent_mapping_and_initialization_are_deterministic(self) -> None:
        owner = {
            argument_id: row["viewpoint_id"]
            for row in self.data["viewpoint_mapping"]["viewpoints"]
            for argument_id in row["argument_ids"]
        }
        for row in self.trace["argument_subagents"].values():
            self.assertEqual([owner[row["argument_id"]]], row["parent_viewpoint_ids"])
        hierarchy_a = AgentHierarchy(self.data, self.trace["argument_catalog"])
        hierarchy_b = AgentHierarchy(self.data, self.trace["argument_catalog"])
        self.assertEqual(hierarchy_a.trace_mapping(), hierarchy_b.trace_mapping())

    def test_macro_aggregate_counts_and_confidence(self) -> None:
        step = self.trace["timestamps"][-1]["steps"][-1]
        for macro in step["viewpoint_macro_agents"].values():
            status_total = (
                macro["accepted_count"] + macro["rejected_count"]
                + macro["undecided_count"] + macro["retracted_count"]
            )
            self.assertEqual(len(macro["argument_agent_ids"]), status_total)
            self.assertGreaterEqual(macro["mean_confidence"], 0.0)
            self.assertLessEqual(macro["mean_confidence"], 1.0)
            self.assertIn("split_contributors", macro)

    @staticmethod
    def _agent(argument_id: str, parent: str) -> ArgumentSubAgent:
        return ArgumentSubAgent(
            agent_id=f"ARG-{argument_id}", argument_id=argument_id,
            parent_viewpoint_ids=[parent], argument_type="A_D",
            belief_status="undecided", confidence=0.5, active=True,
            introduced_at="t1", source_ids=["S"],
        )

    @staticmethod
    def _interaction() -> dict:
        return {
            "interaction_id": "INT-1", "action_id": "ACT-1", "timestamp": "t1",
            "deliberation_step": 0, "action_type": "SUPPORT",
            "source_argument_id": "A", "target_argument_id": "B",
            "relation_ids": ["R"], "evidence_source_ids": ["S"],
            "provenance": {"argument_ids": ["A", "B"]},
        }

    def test_zero_delay_queue_delivers_immediately_and_observation_is_gated(self) -> None:
        queue = DeterministicMessageQueue(["t1", "t2"], PropagationConfig())
        source, target = self._agent("A", "VP1"), self._agent("B", "VP2")
        message = queue.send_from_interaction(self._interaction(), source, target, 2)
        self.assertEqual("queued", message.delivery_status)
        self.assertEqual([], target.inbox)
        delivered = queue.deliver("t1", 0, {"A": source, "B": target})
        self.assertEqual([message], delivered)
        self.assertEqual([message.message_id], target.inbox)
        consumed = queue.consume(target, "t1", 0)
        self.assertEqual([message], consumed)
        self.assertEqual("consumed", message.delivery_status)

    def test_fixed_delay_and_cross_snapshot_carry_are_deterministic(self) -> None:
        config = PropagationConfig(mode="fixed_delay", default_delay_steps=2)
        queue = DeterministicMessageQueue(["t1", "t2"], config)
        source, target = self._agent("A", "VP1"), self._agent("B", "VP2")
        message = queue.send_from_interaction(self._interaction(), source, target, 2)
        self.assertEqual(("t2", 0), (message.available_at_t, message.available_at_k))
        self.assertTrue(message.crossed_snapshot_boundary)
        self.assertEqual([], queue.deliver("t1", 1, {"A": source, "B": target}))
        self.assertEqual([message], queue.deliver("t2", 0, {"A": source, "B": target}))
        self.assertNotIn("date", message.to_dict())

    def test_delay_preserves_remainder_across_multiple_snapshots(self) -> None:
        config = PropagationConfig(mode="fixed_delay", default_delay_steps=7)
        queue = DeterministicMessageQueue(
            ["t1", "t2", "t3", "t4"],
            config,
            {"t1": 2, "t2": 3, "t3": 2, "t4": 4},
        )
        source, target = self._agent("A", "VP1"), self._agent("B", "VP2")
        message = queue.send_from_interaction(self._interaction(), source, target, 2)
        self.assertEqual(("t4", 0), (message.available_at_t, message.available_at_k))
        self.assertTrue(message.crossed_snapshot_boundary)
        self.assertEqual([], queue.deliver("t3", 1, {"A": source, "B": target}))
        self.assertEqual([message], queue.deliver("t4", 0, {"A": source, "B": target}))

    def test_delay_beyond_final_snapshot_remains_pending(self) -> None:
        config = PropagationConfig(mode="fixed_delay", default_delay_steps=9)
        queue = DeterministicMessageQueue(
            ["t1", "t2"], config, {"t1": 2, "t2": 3}
        )
        source, target = self._agent("A", "VP1"), self._agent("B", "VP2")
        message = queue.send_from_interaction(self._interaction(), source, target, 2)
        self.assertEqual(("t2", 7), (message.available_at_t, message.available_at_k))
        self.assertEqual([], queue.deliver("t2", 2, {"A": source, "B": target}))
        self.assertEqual("queued", message.delivery_status)

    def test_negative_delay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PropagationConfig(mode="fixed_delay", default_delay_steps=-1)

    def test_messages_are_ordered_and_trace_has_delivery_states(self) -> None:
        ids = [row["message_id"] for row in self.trace["message_trace"]]
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(self.trace["message_trace"])
        for row in self.trace["message_trace"]:
            self.assertIn(row["delivery_status"], {"queued", "delivered", "consumed"})
            self.assertEqual("unknown", row["provenance"]["real_world_exposure"])

    def test_arrival_steering_zero_delay_reproduces_society_t(self) -> None:
        evaluator = ArrivalAwareSteeringEvaluator(
            self.data, self.snapshots, self.trace,
            DEFAULT_SOCIETY_CONFIG.steering,
            PropagationConfig(),
        )
        pair = evaluator.pairwise("CTQ-A004", "CTQ-A006", 0, 5)
        self.assertEqual(pair["publication_precedence"], pair["arrival_precedence"])
        self.assertEqual(pair["T_delta"], pair["T"])
        self.assertEqual(round(pair["T_delta"] * pair["L"] * pair["P"], 4), pair["I"])

    def test_positive_delay_can_remove_temporal_precedence(self) -> None:
        evaluator = ArrivalAwareSteeringEvaluator(
            self.data, self.snapshots, self.trace, DEFAULT_SOCIETY_CONFIG.steering,
            PropagationConfig(mode="fixed_delay", default_delay_steps=2),
        )
        pair = evaluator.pairwise("CTQ-A004", "CTQ-A006", 0, 5)
        self.assertEqual(1.0, pair["publication_precedence"])
        self.assertEqual(0.0, pair["T_delta"])
        self.assertEqual(0.0, pair["I"])
        self.assertEqual("unknown", pair["real_world_exposure"])

    def test_conflict_risk_and_snapshot_windows_are_preserved(self) -> None:
        comparison = self.trace["zero_delay_baseline_comparison"]
        self.assertTrue(comparison["conflict_unchanged"])
        self.assertFalse(comparison["steering_changed"])
        self.assertFalse(comparison["risk_changed"])
        self.assertEqual(21, len(self.trace["risk_monitoring"]["by_window"]))
        self.assertEqual(
            "RS(x,H)=alpha*C(x,H)+beta*S(x,H)+gamma*C(x,H)*S(x,H)",
            next(iter(self.trace["risk_monitoring"]["by_window"].values()))[
                "ranked_arguments"
            ][0]["risk_detail"]["formula"],
        )

    def test_trace_validation(self) -> None:
        result = validate_hierarchy_trace(self.trace, self.data, self.snapshots)
        self.assertEqual(27, result["argument_subagents"])
        self.assertEqual(21, result["hierarchy_risk_windows"])

    def test_ui_keeps_baseline_risk_and_adds_collapsed_hierarchy(self) -> None:
        self.assertIn("const expandedViewpoints=new Set(", HTML)
        self.assertIn("argument-subagent", HTML)
        self.assertIn("INSPECTOR TRUYỀN TIN", HTML)
        self.assertIn("Giám sát rủi ro", HTML)
        self.assertIn("snapshot_options", HTML)
        self.assertIn("split_contributors", str(self.trace["argument_subagents"]) + str(
            self.trace["timestamps"][-1]["steps"][-1]["viewpoint_macro_agents"]
        ))
        self.assertIn("initNodeDragging", HTML)


if __name__ == "__main__":
    unittest.main()
