"""Portable regression tests for the local WSDM integration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from llm import (  # noqa: E402
    EXTRACT_TASK,
    MAX_EVIDENCE_SPAN_CHARS,
    LLMClient,
    MockClient,
    extract_pair_with_retry,
    render_pair,
    run_extraction,
    validate_extraction,
)
from steering import (  # noqa: E402
    Comment,
    CosineScorer,
    Item,
    ProposedScorer,
    ReplyQuoteScorer,
    load_extractions,
    load_items,
)

PILOT = HERE / "pilot" / "items_unlabeled.jsonl"


class SequenceClient(LLMClient):
    model = "sequence-test"

    def __init__(self, responses):
        self.responses = iter(responses)

    def complete(self, prompt: str, system: str = "") -> str:
        return next(self.responses)


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

    def test_validation_rejects_contradictory_uptake_fields(self):
        item = Item(
            item_id="x", thread_id="t",
            B=Comment(id="b", text="B challenges the premise.", timestamp=2, parent_id="a"),
            candidates={
                "A1": Comment(id="a", text="The premise is costly.", timestamp=1, hops=1),
                "A2": Comment(id="unused", text="", timestamp=1),
            },
            label="unlabeled",
        )
        extraction = {
            "frame_A": {"aspect": "premise", "lens": "cost"},
            "frame_B": {"aspect": "premise", "lens": "cost"},
            "span_A": "The premise is costly.", "span_B": "B challenges the premise.",
            "span_pair_ok": False, "specific_reference": False,
            "uptake_level": "indirect_specific", "uptake_type": "indirect",
            "d_aspect": 1, "d_lens": 1, "development": "new_reason",
        }
        errors = validate_extraction(extraction, item, "A1")
        self.assertIn("span_pair_ok=false requires uptake_level='none'", errors)
        self.assertIn("uptake_level='indirect_specific' requires span_pair_ok=true", errors)
        self.assertIn("uptake_level='indirect_specific' requires specific_reference=true", errors)

    def test_validation_rejects_overlong_evidence_without_normalizing_it(self):
        item = self.items[0]
        extraction = json.loads(MockClient().complete(
            "TASK: EXTRACT\n\n" + render_pair(item, "A1")
        ))
        extraction["span_A"] = item.candidates["A1"].text[:MAX_EVIDENCE_SPAN_CHARS + 1]
        errors = validate_extraction(extraction, item, "A1")
        self.assertTrue(any("select a concise verbatim span" in error for error in errors))
        self.assertEqual(item.candidates["A1"].text[:MAX_EVIDENCE_SPAN_CHARS + 1], extraction["span_A"])

    def test_retry_preserves_initial_failure_and_accepts_valid_correction(self):
        item = Item(
            item_id="x", thread_id="t",
            B=Comment(id="b", text="Path denial is a good point.", timestamp=2, parent_id="a"),
            candidates={
                "A1": Comment(id="a", text="He denies paths.", timestamp=1, hops=1),
                "A2": Comment(id="unused", text="", timestamp=1),
            },
            label="unlabeled",
        )
        invalid = {
            "frame_A": {"aspect": "paths", "lens": "denial"},
            "frame_B": {"aspect": "paths", "lens": "denial"},
            "span_A": "He denies paths.", "span_B": "Path denial is a good point.",
            "span_pair_ok": True, "specific_reference": True,
            "uptake_level": "named_premise", "uptake_type": "indirect_reply",
            "d_aspect": 1, "d_lens": 1, "development": "none",
        }
        valid = {**invalid, "uptake_type": "direct_reply"}
        client = SequenceClient([json.dumps(invalid), json.dumps(valid)])
        extraction, attempts = extract_pair_with_retry(client, item, "A1", max_retries=1)
        self.assertTrue(extraction["validation"]["valid"])
        self.assertEqual(2, len(attempts))
        self.assertFalse(attempts[0]["valid"])
        self.assertIn("uptake_type must be one of", attempts[0]["errors"][0])
        self.assertEqual(json.dumps(invalid), attempts[0]["raw_response"])
        self.assertTrue(attempts[1]["valid"])

    def test_prompt_defines_lens_shift_as_zero(self):
        self.assertIn("switches criteria", EXTRACT_TASK)
        self.assertIn("d_lens=1 only", EXTRACT_TASK)

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
