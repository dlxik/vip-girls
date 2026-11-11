from __future__ import annotations

import unittest

from society.viewpoint_dynamics import RuntimeSocietyStructure


class RuntimeSocietyStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.structure = RuntimeSocietyStructure({
            "viewpoints": [
                {"viewpoint_id": "VP-A", "argument_ids": ["A1", "A2"]},
                {"viewpoint_id": "VP-B", "argument_ids": ["A3"]},
            ]
        })

    def test_split_retires_parent_and_creates_active_children(self) -> None:
        children = self.structure.register_split(
            "VP-A", [["A1"], ["A2"]], "t2", 1, "trigger-split"
        )
        snapshot = self.structure.snapshot()
        self.assertFalse(snapshot["runtime_viewpoints"]["VP-A"]["active"])
        self.assertEqual(set(children), set(snapshot["active_viewpoint_ids"]) - {"VP-B"})

    def test_merge_retires_parents_and_creates_active_result(self) -> None:
        merged = self.structure.register_merge(
            ["VP-A", "VP-B"], ["A1", "A2", "A3"], "t3", 2, "trigger-merge"
        )
        snapshot = self.structure.snapshot()
        self.assertFalse(snapshot["runtime_viewpoints"]["VP-A"]["active"])
        self.assertFalse(snapshot["runtime_viewpoints"]["VP-B"]["active"])
        self.assertEqual(snapshot["active_viewpoint_ids"], [merged])


if __name__ == "__main__":
    unittest.main()
