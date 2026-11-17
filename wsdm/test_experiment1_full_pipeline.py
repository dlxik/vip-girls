"""Offline regression tests for full Experiment 1 checkpointing and evaluation."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import approved_detection_experiment as experiment  # noqa: E402


def _model_inputs(n: int) -> pd.DataFrame:
    rows = []
    for index in range(n):
        rows.append({
            "argument_pair_id": f"TEST-{index:03d}",
            "original_pair_id": f"PAIR-{index:03d}",
            "thread_id": f"THREAD-{index:03d}",
            "A_id": f"A-{index:03d}", "B_id": f"B-{index:03d}",
            "A_text": "shared premise supports this policy",
            "B_text": "shared premise supports this policy because it helps",
            "permitted_context_json": "[]",
            "context_status": "unavailable_in_approved_source",
            "structure_relation": "direct_reply",
            "relation_source": "test",
            "temporal_order_verified": "TRUE",
            "input_condition": "human_segmented",
            "human_segmentation_used": "TRUE",
        })
    return pd.DataFrame(rows, columns=experiment.INPUT_COLUMNS)


class FullExperimentPipelineTests(unittest.TestCase):
    def test_model_input_rejects_gold_columns_before_inference(self):
        inputs = _model_inputs(1)
        inputs["label_binary"] = [1]
        with self.assertRaisesRegex(ValueError, "Gold/prediction fields are forbidden"):
            experiment._assert_model_input(inputs)

    def test_cli_allows_at_most_one_correction_retry(self):
        action = next(
            action for action in experiment.build_parser()._subparsers._group_actions[0]
            .choices["extract-proposed"]._actions
            if action.dest == "max_extraction_retries"
        )
        self.assertEqual((0, 1), action.choices)

    def test_atomic_checkpoints_resume_without_duplicate_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs_path = root / "inputs.csv"
            output_path = root / "run"
            experiment._write_csv(_model_inputs(2), inputs_path)
            args = argparse.Namespace(
                inputs=str(inputs_path), model="mock", out=str(output_path),
                max_extraction_retries=1, expected_items=2,
                model_artifact_digest="mock-digest", resume=False,
            )
            experiment.extract_proposed(args)
            attempts_before = (output_path / "extraction_attempts.jsonl").read_text(encoding="utf-8")
            self.assertEqual(2, len(list((output_path / "item_checkpoints").glob("*.json"))))
            self.assertEqual(2, len(experiment._read_jsonl(output_path / "extractions.jsonl")))
            manifest = json.loads((output_path / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["completed"])
            self.assertEqual(2, manifest["n_processed"])
            self.assertEqual("mock-digest", manifest["run_configuration"]["model_artifact_digest"])
            args.resume = True
            experiment.extract_proposed(args)
            attempts_after = (output_path / "extraction_attempts.jsonl").read_text(encoding="utf-8")
            self.assertEqual(attempts_before, attempts_after)

    def test_post_inference_evaluation_keeps_failures_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold = pd.DataFrame({
                "argument_pair_id": [f"TEST-{i:03d}" for i in range(41)],
                "label_text": ["YES"] * 32 + ["NO"] * 9,
                "label_binary": [1] * 32 + [0] * 9,
            })
            failed_id = "TEST-040"
            methods = ["proposed", "proposed_u_only", "proposed_d_only",
                       "proposed_ungated", "proposed_dmean"]
            predictions = []
            for row in gold.loc[gold.argument_pair_id.ne(failed_id)].itertuples(index=False):
                for method in methods:
                    predictions.append({
                        "argument_pair_id": row.argument_pair_id,
                        "input_condition": "human_segmented", "method": method,
                        "score": float(row.label_binary), "G": 1, "U": 1.0,
                        "U_raw": 1.0, "D": 1.0, "d_aspect": 1.0, "d_lens": 1.0,
                    })
            baseline = pd.DataFrame([{
                "argument_pair_id": row.argument_pair_id,
                "input_condition": "human_segmented", "method": "tfidf_word",
                "score": float(index) / 41,
            } for index, row in enumerate(gold.itertuples(index=False))])
            evidence = pd.DataFrame([{
                "argument_pair_id": row.argument_pair_id,
                "input_condition": "human_segmented", "status": "valid",
                "score": float(row.label_binary), "G": 1, "U": 1.0,
                "U_raw": 1.0, "D": 1.0, "d_aspect": 1.0, "d_lens": 1.0,
                "span_A": "shared premise", "span_B": "shared premise",
            } for row in gold.loc[gold.argument_pair_id.ne(failed_id)].itertuples(index=False)])
            gold_path, predictions_path = root / "gold.csv", root / "predictions.csv"
            baseline_path, evidence_path = root / "baseline.csv", root / "evidence.csv"
            errors_path, attempts_path = root / "errors.jsonl", root / "attempts.jsonl"
            experiment._write_csv(gold, gold_path)
            experiment._write_csv(pd.DataFrame(predictions), predictions_path)
            experiment._write_csv(baseline, baseline_path)
            experiment._write_csv(evidence, evidence_path)
            errors_path.write_text(json.dumps({
                "argument_pair_id": failed_id, "errors": ["terminal test failure"],
                "attempt_count": 2,
            }) + "\n", encoding="utf-8")
            attempts_path.write_text("".join(json.dumps({
                "argument_pair_id": item_id, "attempt": 1, "valid": item_id != failed_id,
            }) + "\n" for item_id in gold.argument_pair_id), encoding="utf-8")
            output = root / "evaluation"
            experiment.evaluate_proposed(argparse.Namespace(
                predictions=str(predictions_path), gold=str(gold_path),
                errors=str(errors_path), attempts=str(attempts_path),
                evidence=str(evidence_path), baseline_predictions=str(baseline_path),
                out=str(output),
            ))
            summary = json.loads((output / "proposed_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(40, summary["n_scored"])
            self.assertEqual(1, summary["n_failed_extractions"])
            self.assertAlmostEqual(40 / 41, summary["initial_valid_coverage"])
            self.assertEqual(0, summary["n_items_retried"])
            evaluated = experiment._read_csv(output / "item_level_evaluation.csv")
            failed = evaluated.loc[evaluated.argument_pair_id.eq(failed_id)].iloc[0]
            self.assertEqual("failed", failed.extraction_status)
            self.assertEqual("", failed.score)
            self.assertTrue((output / "experiment1_full_report.md").exists())
            report = (output / "experiment1_full_report.md").read_text(encoding="utf-8")
            self.assertIn("gated retention", report)
            self.assertIn("can be degenerate", report)
            comparison = experiment._read_csv(output / "baseline_proposed_comparison.csv")
            self.assertTrue((comparison.n.astype(int) == 40).all())
            self.assertTrue((output / "missing_score_sensitivity.csv").exists())
            self.assertTrue((output / "error_analysis.csv").exists())


if __name__ == "__main__":
    unittest.main()
