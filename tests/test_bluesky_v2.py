from __future__ import annotations

import json
import unittest

from bluesky.src.loader import load_ctq_data
from bluesky.src.temporal_graph import build_temporal_snapshots
from bluesky.src.viewpoint import add_viewpoint_layers
from bluesky.v2.agent import initialize_agents
from bluesky.v2.config import DEFAULT_CONFIG
from bluesky.v2.simulation import AutonomousArgumentationSimulation
from bluesky.v2.validation import validate_trace_provenance
from bluesky.v2.visualizer_v2 import HTML


class AutonomousArgumentationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_ctq_data()
        cls.snapshots = build_temporal_snapshots(cls.data)
        add_viewpoint_layers(cls.snapshots, cls.data["viewpoint_mapping"])
        cls.trace = AutonomousArgumentationSimulation(cls.data, cls.snapshots).run()

    def run_at(self, timestamp: str) -> dict:
        return next(row for row in self.trace["timestamps"] if row["timestamp"] == timestamp)

    def test_agent_initialization(self) -> None:
        agents = initialize_agents(
            self.data["viewpoint_mapping"], self.snapshots[0], DEFAULT_CONFIG
        )
        self.assertEqual(9, len(agents))
        self.assertEqual(5, sum(len(agent.belief_base) for agent in agents.values()))
        self.assertEqual("contextual", agents["CTX01"].kind)

    def test_argument_catalog_preserves_node_details(self) -> None:
        catalog = self.trace["argument_catalog"]
        self.assertEqual(27, len(catalog))
        self.assertIn("premise", catalog["CTQ-A015"])
        self.assertIn("rule", catalog["CTQ-A015"])
        self.assertIn("conclusion", catalog["CTQ-A015"])
        self.assertTrue(catalog["CTQ-A015"]["source_ids"])

    def test_visualizer_exposes_node_and_edge_inspection(self) -> None:
        self.assertIn('id="hoverTip"', HTML)
        self.assertIn('class="edge-hit"', HTML)
        self.assertIn("function interactionPanel()", HTML)
        self.assertIn("Bấm cạnh để xem P/R/C", HTML)
        self.assertIn("previousFrame", HTML)
        self.assertIn("đang giữ trạng thái trước", HTML)
        self.assertIn("đang áp dụng thêm/bớt", HTML)

    def test_observation_generation(self) -> None:
        step = self.run_at("t4")["steps"][0]
        observation = step["observations"]["VP04"]
        self.assertIn("CTQ-R024", observation["provenance"]["relation_ids"])
        self.assertEqual("t4", observation["current_temporal_context"]["timestamp_id"])
        self.assertTrue(observation["current_temporal_context"]["real_time_not_simulation_round"])

    def test_reasoning_is_deterministic(self) -> None:
        again = AutonomousArgumentationSimulation(self.data, self.snapshots).run()
        self.assertEqual(
            json.dumps(self.trace, sort_keys=True, ensure_ascii=False),
            json.dumps(again, sort_keys=True, ensure_ascii=False),
        )

    def test_candidate_action_generation(self) -> None:
        candidates = self.run_at("t4")["steps"][0]["candidate_actions"]["VP04"]
        types = {row["action_type"] for row in candidates}
        self.assertTrue({"ATTACK", "CHALLENGE", "NO_OP"}.issubset(types))
        attack = next(row for row in candidates if row["action_type"] == "ATTACK")
        self.assertEqual(["CTQ-R024"], attack["relation_ids"])

    def test_action_validation_and_selection(self) -> None:
        step = self.run_at("t4")["steps"][0]
        selected = step["selected_actions"]["VP04"]
        self.assertTrue(selected["valid"])
        self.assertEqual("Grounding hợp lệ.", selected["validation_reason"])
        self.assertEqual("ATTACK", selected["action_type"])
        non_noop = [row for row in step["candidate_actions"]["VP04"] if row["action_type"] != "NO_OP"]
        self.assertEqual(max(row["utility"] for row in non_noop), selected["utility"])

    def test_provenance_integrity(self) -> None:
        counts = validate_trace_provenance(self.trace, self.data, self.snapshots)
        self.assertGreater(counts["actions"], 0)
        self.assertGreater(counts["interactions"], 0)
        self.assertGreater(counts["revisions"], 0)

    def test_belief_revision_and_status_separation(self) -> None:
        step = self.run_at("t4")["steps"][0]
        revision = next(
            row for row in step["belief_revisions"]
            if row["agent_id"] == "VP06" and row["argument_id"] == "CTQ-A015"
        )
        self.assertIn("ACT-t4-k0-VP04-001", revision["trigger_action_ids"])
        self.assertLess(revision["new_confidence"], revision["old_confidence"])
        self.assertEqual("accepted", revision["canonical_status"])
        self.assertNotEqual(
            revision["canonical_status"],
            step["agent_states_after"]["VP06"]["belief_states"]["CTQ-A015"]["agent_belief_status"],
        )

    def test_convergence_detection(self) -> None:
        t1 = self.run_at("t1")
        self.assertEqual("all_agents_no_op", t1["stop_reason"])
        self.assertLessEqual(t1["steps_executed"], DEFAULT_CONFIG.max_deliberation_steps)
        valid_reasons = {"all_agents_no_op", "no_belief_change_and_repeated_state", "max_steps_reached"}
        self.assertTrue(all(row["stop_reason"] in valid_reasons for row in self.trace["timestamps"]))

    def test_transition_t1_to_t2(self) -> None:
        step = self.run_at("t2")["steps"][0]
        self.assertIn("CTQ-A006", step["observations"]["VP02"]["newly_introduced_arguments"])
        self.assertTrue(any(row["target_argument_id"] == "CTQ-A004" for row in step["interactions"]))

    def test_transition_t3_to_t4(self) -> None:
        step = self.run_at("t4")["steps"][0]
        interaction = next(row for row in step["interactions"] if row["actor_agent"] == "VP04")
        self.assertEqual(("ATTACK", "VP06"), (interaction["action_type"], interaction["target_agent"]))
        self.assertEqual(["CTQ-R024"], interaction["relation_ids"])

    def test_transition_t5_to_t6(self) -> None:
        t6 = self.run_at("t6")
        interactions = [row for step in t6["steps"] for row in step["interactions"]]
        systemic = [row for row in interactions if row["actor_agent"] == "VP08"]
        self.assertTrue(systemic)
        self.assertTrue(any(set(row["relation_ids"]) & {"CTQ-R029", "CTQ-R030", "CTQ-R031"} for row in systemic))

    def test_society_metrics_are_bounded(self) -> None:
        for run in self.trace["timestamps"]:
            for step in run["steps"]:
                metrics = step["society_metrics"]
                self.assertGreaterEqual(metrics["mean_internal_belief_confidence"], 0.0)
                self.assertLessEqual(metrics["mean_internal_belief_confidence"], 1.0)
                self.assertGreaterEqual(metrics["conflict_intensity"], 0.0)
                self.assertLessEqual(metrics["conflict_intensity"], 1.0)

    def test_ui_supports_persistent_node_dragging(self) -> None:
        self.assertIn("function initNodeDragging()", HTML)
        self.assertIn("manualPositions:loadLayout()", HTML)
        self.assertIn("layoutStorageKey", HTML)
        self.assertIn("resetLayout", HTML)


if __name__ == "__main__":
    unittest.main()
