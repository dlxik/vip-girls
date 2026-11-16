"""Portable regression tests for the local WSDM integration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from llm import MockClient, render_pair, run_extraction, validate_extraction  # noqa: E402
from steering import (  # noqa: E402
    CosineScorer,
    ProposedScorer,
    ReplyQuoteScorer,
    load_extractions,
    load_items,
)

PILOT = HERE / "pilot" / "items_unlabeled.jsonl"


class RealPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = load_items(str(PILOT), allow_unlabeled=True)

    def test_real_pilot_shape_and_temporal_constraints(self):
        self.assertEqual(50, len(self.items))
        self.assertEqual(25, len({item.thread_id for item in self.items}))
        self.assertEqual(len(self.items), len({item.item_id for item in self.items}))
        for item in self.items:
            self.assertEqual("unlabeled", item.label)
            self.assertTrue(all(a.timestamp < item.B.timestamp for a in item.candidates.values()))
            self.assertTrue(all(c.timestamp <= item.B.timestamp for c in item.context))

    def test_baselines_complete(self):
        for scorer in (CosineScorer(), ReplyQuoteScorer()):
            scorer.fit(self.items)
            scores = [scorer.score(item, key) for item in self.items for key in ("A1", "A2")]
            self.assertEqual(100, len(scores))
            self.assertTrue(all(0 <= score <= 1 for score in scores))

    def test_prompt_does_not_expose_gold_label(self):
        item = self.items[0]
        original = item.label
        try:
            item.label = "SENTINEL_GOLD_LABEL"
            prompt = render_pair(item, "A1")
            self.assertNotIn("SENTINEL_GOLD_LABEL", prompt)
        finally:
            item.label = original

    def test_span_validation_rejects_nonverbatim_claim(self):
        item = self.items[0]
        extraction = json.loads(MockClient().complete(
            "TASK: EXTRACT\n\n" + render_pair(item, "A1")
        ))
        extraction["span_A"] = "not a verbatim source span"
        errors = validate_extraction(extraction, item, "A1")
        self.assertIn("span_A is not a verbatim substring of A", errors)

    def test_mock_extraction_and_all_ablations(self):
        with tempfile.TemporaryDirectory() as directory:
            extraction_path = Path(directory) / "extractions.jsonl"
            error_path = Path(directory) / "errors.jsonl"
            selected = self.items[:2]
            self.assertEqual(
                4,
                run_extraction(selected, MockClient(), str(extraction_path), str(error_path)),
            )
            extraction_map = load_extractions(str(extraction_path))
            self.assertEqual(4, len(extraction_map))
            for variant in ProposedScorer.VARIANTS:
                scorer = ProposedScorer(extraction_map, variant)
                values = [scorer.score(item, key) for item in selected for key in ("A1", "A2")]
                self.assertTrue(all(0 <= value <= 1 for value in values))


if __name__ == "__main__":
    unittest.main()
