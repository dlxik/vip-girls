"""Experiment 1 utilities for approved CMV argument-level steering detection.

The ranking task is intentionally out of scope.  This module keeps model inputs,
gold labels, predictions, and evaluation outputs in separate files.

Subcommands:
  prepare            build the 41-unit manifest and two input conditions
  baselines          run non-LLM descriptive baselines for both conditions
  extract-proposed   run G/U/D extraction without accepting a gold-label path
  evaluate-proposed  join proposed scores to gold only after inference
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score


REQUIRED_ANNOTATION_COLUMNS = {
    "argument_pair_id", "original_pair_id", "alignment_index", "thread_id",
    "A_id", "B_id", "A_comment", "B_comment", "A_argument_span",
    "B_argument_span", "unit_approved", "review_status", "final_steering",
    "temporal_status", "sampling_stratum",
}
INPUT_COLUMNS = [
    "argument_pair_id", "original_pair_id", "thread_id", "A_id", "B_id",
    "A_text", "B_text", "permitted_context_json", "context_status",
    "structure_relation", "relation_source", "temporal_order_verified",
    "input_condition", "human_segmentation_used",
]
FORBIDDEN_INPUT_COLUMN_FRAGMENTS = (
    "label", "steering", "evidence", "adjudication", "review_status",
    "unit_approved", "prediction", "score",
)
BASELINE_METHODS = (
    "tfidf_word", "tfidf_char", "token_jaccard", "reply_only",
    "hash_random_sanity",
)


def _read_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, encoding="utf-8-sig")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write a complete checkpoint artifact without exposing a partial file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _atomic_write_json(path: Path, value: dict) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(path)


def _read_jsonl(path: str | Path) -> list[dict]:
    records = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return records


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def _assert_model_input(frame: pd.DataFrame) -> None:
    missing = set(INPUT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Model input missing columns: {sorted(missing)}")
    forbidden = [
        name for name in frame.columns
        if any(fragment in name.lower() for fragment in FORBIDDEN_INPUT_COLUMN_FRAGMENTS)
    ]
    if forbidden:
        raise ValueError(f"Gold/prediction fields are forbidden in model inputs: {forbidden}")
    if frame.argument_pair_id.duplicated().any():
        raise ValueError("Duplicate argument_pair_id in model input")
    if not frame.temporal_order_verified.astype(str).str.upper().eq("TRUE").all():
        raise ValueError("Every prepared record must have verified A-before-B order")


def _validate_annotations(source: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_ANNOTATION_COLUMNS - set(source.columns)
    if missing:
        raise ValueError(f"Annotation file missing columns: {sorted(missing)}")
    if len(source) != 60:
        raise ValueError(f"Expected 60 approved rows, found {len(source)}")
    if source.argument_pair_id.duplicated().any():
        raise ValueError("argument_pair_id must be unique")
    if not source.review_status.eq("APPROVED").all():
        raise ValueError("Every source row must be APPROVED")
    if not source.unit_approved.isin(["YES", "NO"]).all():
        raise ValueError("Unexpected unit_approved value")
    if not source.temporal_status.eq("valid_order").all():
        raise ValueError("Temporal order is not valid for every approved row")

    eligible = source.loc[
        source.unit_approved.eq("YES")
        & source.final_steering.isin(["YES", "NO"])
    ].copy()
    if len(eligible) != 41:
        raise ValueError(f"Expected 41 binary approved units, found {len(eligible)}")
    for span_col, raw_col in (
        ("A_argument_span", "A_comment"), ("B_argument_span", "B_comment")
    ):
        if eligible[span_col].str.strip().eq("").any():
            raise ValueError(f"Eligible rows contain blank {span_col}")
        bad = eligible.apply(lambda row: row[span_col] not in row[raw_col], axis=1)
        if bad.any():
            ids = eligible.loc[bad, "argument_pair_id"].tolist()
            raise ValueError(f"Human segment is not verbatim source text: {ids}")
    return eligible


def prepare(args: argparse.Namespace) -> None:
    source_path = Path(args.annotations).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output directory already exists: {out}")
    source = _read_csv(source_path)
    eligible = _validate_annotations(source)

    pair_sizes = eligible.groupby("original_pair_id").size().to_dict()
    pair_labels = eligible.groupby("original_pair_id").final_steering.apply(set).to_dict()
    eligible["permitted_context_json"] = "[]"
    eligible["context_status"] = "unavailable_in_approved_source"
    eligible["structure_relation"] = "direct_reply"
    eligible["relation_source"] = "documented_source_sampling_design"
    eligible["temporal_order_verified"] = "TRUE"
    eligible["human_segmentation_required_for_unit_task"] = "TRUE"
    eligible["raw_input_collision_group_size"] = eligible.original_pair_id.map(pair_sizes)
    eligible["raw_input_label_conflict"] = eligible.original_pair_id.map(
        lambda key: "TRUE" if len(pair_labels[key]) > 1 else "FALSE"
    )

    manifest_columns = [
        "argument_pair_id", "original_pair_id", "alignment_index", "thread_id",
        "A_id", "B_id", "A_comment", "B_comment", "A_argument_span",
        "B_argument_span", "permitted_context_json", "context_status",
        "structure_relation", "relation_source", "temporal_status",
        "temporal_order_verified", "sampling_stratum", "final_steering",
        "human_segmentation_required_for_unit_task",
        "raw_input_collision_group_size", "raw_input_label_conflict",
    ]
    manifest = eligible[manifest_columns].copy()

    common = eligible[[
        "argument_pair_id", "original_pair_id", "thread_id", "A_id", "B_id",
        "permitted_context_json", "context_status", "structure_relation",
        "relation_source", "temporal_order_verified",
    ]].copy()
    raw_inputs = common.copy()
    raw_inputs["A_text"] = eligible.A_comment
    raw_inputs["B_text"] = eligible.B_comment
    raw_inputs["input_condition"] = "raw_comment"
    raw_inputs["human_segmentation_used"] = "FALSE"
    raw_inputs = raw_inputs[INPUT_COLUMNS]

    segmented_inputs = common.copy()
    segmented_inputs["A_text"] = eligible.A_argument_span
    segmented_inputs["B_text"] = eligible.B_argument_span
    segmented_inputs["input_condition"] = "human_segmented"
    segmented_inputs["human_segmentation_used"] = "TRUE"
    segmented_inputs = segmented_inputs[INPUT_COLUMNS]
    _assert_model_input(raw_inputs)
    _assert_model_input(segmented_inputs)

    gold = eligible[["argument_pair_id", "final_steering"]].copy()
    gold = gold.rename(columns={"final_steering": "label_text"})
    gold["label_binary"] = gold.label_text.eq("YES").astype(int)

    out.mkdir(parents=True)
    _write_csv(manifest, out / "evaluation_manifest.csv")
    _write_csv(raw_inputs, out / "model_inputs_raw_comment.csv")
    _write_csv(segmented_inputs, out / "model_inputs_human_segmented.csv")
    _write_csv(gold, out / "gold_labels.csv")

    multi_pairs = {
        key: group.argument_pair_id.tolist()
        for key, group in eligible.groupby("original_pair_id") if len(group) > 1
    }
    mixed_pairs = {
        key: group[["argument_pair_id", "final_steering"]].to_dict("records")
        for key, group in eligible.groupby("original_pair_id")
        if group.final_steering.nunique() > 1
    }
    protocol = {
        "task": "Experiment 1: binary evidence-grounded argumentative steering detection",
        "ranking_task_in_scope": False,
        "source_annotations": str(source_path),
        "n_source_approved_rows": int(len(source)),
        "n_binary_argument_units": int(len(eligible)),
        "n_positive": int((gold.label_binary == 1).sum()),
        "n_negative": int((gold.label_binary == 0).sum()),
        "positive_prevalence": float(gold.label_binary.mean()),
        "n_threads": int(eligible.thread_id.nunique()),
        "n_distinct_raw_comment_pairs": int(eligible.original_pair_id.nunique()),
        "multi_unit_comment_pairs": multi_pairs,
        "mixed_label_raw_comment_pairs": mixed_pairs,
        "human_segmentation_required": True,
        "segmentation_reason": (
            "The 41 labels are argument-unit labels. Six raw comment pairs contain multiple "
            "approved units, and CMV-020 has identical raw A/B input with one YES and one NO unit."
        ),
        "input_conditions": {
            "raw_comment": "Diagnostic only; duplicate raw inputs and one conflicting-label pair remain.",
            "human_segmented": (
                "Uses A_argument_span/B_argument_span as human segmentation. It does not use "
                "A_evidence_span/B_evidence_span."
            ),
        },
        "context_policy": (
            "No historical context or raw timestamps are present in the approved CSV. "
            "Prepared prompts therefore use empty context and only the verified valid_order flag."
        ),
        "structure_policy": (
            "All source pairs are documented as direct replies by the existing evaluator; "
            "reply_only is therefore constant."
        ),
        "label_isolation": {
            "model_input_files_contain_labels": False,
            "gold_evidence_spans_used_as_model_inputs": False,
            "gold_file": "gold_labels.csv",
        },
        "scientific_status": "descriptive approved pilot; not held-out generalization",
    }
    _write_json(out / "protocol.json", protocol)
    (out / "README.md").write_text(
        "# Experiment 1 prepared data\n\n"
        "This directory separates model inputs, gold labels, and the evaluation manifest.\n\n"
        "- `model_inputs_raw_comment.csv`: raw-comment diagnostic condition; no labels or gold spans.\n"
        "- `model_inputs_human_segmented.csv`: human-segmented condition; no labels or evidence spans.\n"
        "- `gold_labels.csv`: labels only, joined after prediction.\n"
        "- `evaluation_manifest.csv`: provenance and audit table; never pass this file to a model.\n"
        "- `protocol.json`: limitations and condition definitions.\n\n"
        "Human segmentation is required for the 41-unit task because identical raw comments can "
        "contain multiple argument units; CMV-020 contains both a YES and a NO unit.\n",
        encoding="utf-8",
    )
    print(json.dumps(protocol, indent=2, ensure_ascii=False))
    print(f"PREPARED DATA: {out}")


def _jaccard(a: str, b: str) -> float:
    import re
    ta, tb = (set(re.findall(r"\w+", str(text).lower())) for text in (a, b))
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _hash_random(argument_pair_id: str) -> float:
    digest = hashlib.sha256(argument_pair_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def _condition_scores(inputs: pd.DataFrame) -> pd.DataFrame:
    _assert_model_input(inputs)
    a = inputs.A_text.astype(str).tolist()
    b = inputs.B_text.astype(str).tolist()
    n = len(inputs)
    scores: dict[str, np.ndarray] = {}
    for key, vectorizer in (
        ("tfidf_word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("tfidf_char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True)),
    ):
        fitted = vectorizer.fit_transform(a + b)
        scores[key] = np.asarray(fitted[:n].multiply(fitted[n:]).sum(axis=1)).ravel()
    scores["token_jaccard"] = np.asarray([_jaccard(x, y) for x, y in zip(a, b)])
    scores["reply_only"] = np.ones(n)
    scores["hash_random_sanity"] = np.asarray([
        _hash_random(value) for value in inputs.argument_pair_id.astype(str)
    ])
    rows = []
    condition = inputs.input_condition.iloc[0]
    for method in BASELINE_METHODS:
        for argument_pair_id, score in zip(inputs.argument_pair_id, scores[method]):
            rows.append({
                "argument_pair_id": argument_pair_id,
                "input_condition": condition,
                "method": method,
                "score": float(score),
            })
    return pd.DataFrame(rows)


def _metrics(predictions: pd.DataFrame, gold: pd.DataFrame) -> pd.DataFrame:
    if gold.argument_pair_id.duplicated().any():
        raise ValueError("Duplicate gold argument_pair_id")
    joined = predictions.merge(gold[["argument_pair_id", "label_binary"]],
                               on="argument_pair_id", how="left", validate="many_to_one")
    if joined.label_binary.eq("").any() or joined.label_binary.isna().any():
        raise ValueError("Predictions missing gold labels")
    rows = []
    for (condition, method), group in joined.groupby(["input_condition", "method"]):
        y = group.label_binary.astype(int).to_numpy()
        score = group.score.astype(float).to_numpy()
        rows.append({
            "input_condition": condition,
            "method": method,
            "n": int(len(group)),
            "n_positive": int(y.sum()),
            "n_negative": int(len(y) - y.sum()),
            "positive_prevalence": float(y.mean()),
            "AUROC": float(roc_auc_score(y, score)),
            "average_precision": float(average_precision_score(y, score)),
        })
    return pd.DataFrame(rows).sort_values(["input_condition", "method"])


def baselines(args: argparse.Namespace) -> None:
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output directory already exists: {out}")
    raw_inputs = _read_csv(args.raw_inputs)
    segmented_inputs = _read_csv(args.segmented_inputs)
    gold = _read_csv(args.gold)
    if set(gold.label_text) != {"YES", "NO"}:
        raise ValueError("Gold labels must be YES/NO")
    if len(raw_inputs) != 41 or len(segmented_inputs) != 41 or len(gold) != 41:
        raise ValueError("Both input conditions and gold must contain 41 rows")

    predictions = pd.concat([
        _condition_scores(raw_inputs), _condition_scores(segmented_inputs)
    ], ignore_index=True)
    metric_table = _metrics(predictions, gold)
    out.mkdir(parents=True)
    _write_csv(predictions, out / "baseline_predictions.csv")
    _write_csv(metric_table, out / "baseline_metrics.csv")

    raw_join = raw_inputs.merge(gold, on="argument_pair_id", validate="one_to_one")
    conflict_groups = 0
    for _, group in raw_join.groupby(["A_id", "B_id", "A_text", "B_text"]):
        if group.label_binary.nunique() > 1:
            conflict_groups += 1
    summary = {
        "task": "binary_argument_relation_diagnostics_NOT_pairwise_ranking",
        "status": "approved pilot / descriptive only / not held-out",
        "n": 41,
        "n_threads": int(raw_inputs.thread_id.nunique()),
        "n_positive": int(gold.label_binary.astype(int).sum()),
        "n_negative": int(41 - gold.label_binary.astype(int).sum()),
        "positive_prevalence": float(gold.label_binary.astype(int).mean()),
        "conditions": ["raw_comment", "human_segmented"],
        "methods": list(BASELINE_METHODS),
        "raw_condition_unique_comment_pairs": int(
            raw_inputs[["A_id", "B_id", "A_text", "B_text"]].drop_duplicates().shape[0]
        ),
        "raw_condition_conflicting_label_input_groups": int(conflict_groups),
        "metrics": metric_table.to_dict("records"),
        "caveats": [
            "No held-out split; vocabulary is fit unsupervised on this pilot.",
            "The 41 units come from 34 threads and are not independent observations.",
            "Positive prevalence is high, so Average Precision must be compared with prevalence.",
            "Raw-comment evaluation repeats identical inputs for multi-unit pairs and has one conflicting-label input group.",
            "Human-segmented evaluation uses human argument boundaries and is a separate condition.",
            "reply_only is constant because every source pair is a direct reply.",
            "hash_random_sanity is an ID-based sanity floor, not a substantive model.",
        ],
    }
    _write_json(out / "baseline_summary.json", summary)
    lines = [
        "# Experiment 1 non-LLM baselines", "",
        "Descriptive approved-pilot results only; these are not held-out generalization results.", "",
        f"- N = 41 argument units from {summary['n_threads']} threads.",
        f"- YES = {summary['n_positive']}; NO = {summary['n_negative']}; prevalence = {summary['positive_prevalence']:.3f}.",
        f"- Raw condition has {summary['raw_condition_unique_comment_pairs']} unique A/B comment inputs and {conflict_groups} conflicting-label identical-input group.",
        "", "## Metrics", "",
        "| Input condition | Method | AUROC | Average Precision |", "|---|---:|---:|---:|",
    ]
    for row in summary["metrics"]:
        lines.append(
            f"| {row['input_condition']} | {row['method']} | {row['AUROC']:.3f} | {row['average_precision']:.3f} |"
        )
    lines.extend(["", "## Limitations", ""] + [f"- {x}" for x in summary["caveats"]])
    (out / "baseline_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(metric_table.to_string(index=False))
    print(f"BASELINE RESULTS: {out}")


def _edge_item(row):
    from steering import Comment, Item
    argument_pair_id = str(row.argument_pair_id)
    internal_a_id = f"{row.A_id}::{argument_pair_id}"
    internal_b_id = f"{row.B_id}::{argument_pair_id}"
    a = Comment(id=internal_a_id, text=str(row.A_text), timestamp=0.0,
                parent_id=None, quotes=[], hops=1)
    b = Comment(id=internal_b_id, text=str(row.B_text), timestamp=1.0,
                parent_id=internal_a_id, quotes=[])
    unused = Comment(id=f"unused::{argument_pair_id}", text="", timestamp=0.0,
                     parent_id=None, quotes=[], hops=None)
    return Item(item_id=argument_pair_id, thread_id=str(row.thread_id), B=b,
                candidates={"A1": a, "A2": unused}, label="unlabeled",
                slices=[str(row.input_condition)], context=[])


PREDICTION_COLUMNS = [
    "argument_pair_id", "input_condition", "method", "score", "Temporal",
    "G", "U", "U_raw", "D", "d_aspect", "d_lens",
]
EVIDENCE_COLUMNS = [
    "argument_pair_id", "input_condition", "status", "Temporal", "G", "U",
    "U_raw", "d_aspect", "d_lens", "D", "score", "span_A", "span_B",
    "span_pair_ok", "specific_reference", "uptake_level", "uptake_type",
    "development", "frame_A_aspect", "frame_A_lens", "frame_B_aspect",
    "frame_B_lens", "source_A_id", "source_B_id",
]


def _checkpoint_path(checkpoint_dir: Path, argument_pair_id: str) -> Path:
    digest = hashlib.sha256(argument_pair_id.encode("utf-8")).hexdigest()[:16]
    return checkpoint_dir / f"{digest}.json"


def _score_extraction(item, row, extraction: dict) -> tuple[list[dict], dict]:
    from steering import ProposedScorer, pair_key
    mapping = {pair_key(item.candidates["A1"].id, item.B.id): extraction}
    predictions = []
    full_explanation = None
    for variant in ProposedScorer.VARIANTS:
        scorer = ProposedScorer(mapping, variant)
        explanation = scorer.explain(item, "A1")
        component = explanation["components"]
        predictions.append({
            "argument_pair_id": item.item_id,
            "input_condition": str(row.input_condition),
            "method": scorer.name,
            "score": explanation["S"],
            "Temporal": int(component["time_ok"]),
            "G": component["G"], "U": component["U"],
            "U_raw": component["U_raw"], "D": component["D"],
            "d_aspect": component["d_aspect"], "d_lens": component["d_lens"],
        })
        if variant == "full":
            full_explanation = explanation
    component = full_explanation["components"]
    evidence = {
        "argument_pair_id": item.item_id,
        "input_condition": str(row.input_condition), "status": "valid",
        "Temporal": int(component["time_ok"]), "G": component["G"],
        "U": component["U"], "U_raw": component["U_raw"],
        "d_aspect": component["d_aspect"], "d_lens": component["d_lens"],
        "D": component["D"], "score": full_explanation["S"],
        "span_A": extraction["span_A"], "span_B": extraction["span_B"],
        "span_pair_ok": extraction["span_pair_ok"],
        "specific_reference": extraction["specific_reference"],
        "uptake_level": extraction["uptake_level"],
        "uptake_type": extraction["uptake_type"],
        "development": extraction["development"],
        "frame_A_aspect": extraction["frame_A"]["aspect"],
        "frame_A_lens": extraction["frame_A"]["lens"],
        "frame_B_aspect": extraction["frame_B"]["aspect"],
        "frame_B_lens": extraction["frame_B"]["lens"],
        "source_A_id": str(row.A_id), "source_B_id": str(row.B_id),
    }
    return predictions, evidence


def _load_checkpoints(inputs: pd.DataFrame, checkpoint_dir: Path, config_hash: str) -> list[dict]:
    checkpoints = []
    for argument_pair_id in inputs.argument_pair_id.astype(str):
        path = _checkpoint_path(checkpoint_dir, argument_pair_id)
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("argument_pair_id") != argument_pair_id:
            raise ValueError(f"Checkpoint ID mismatch: {path}")
        if record.get("configuration_sha256") != config_hash:
            raise ValueError(f"Checkpoint configuration hash mismatch: {path}")
        checkpoints.append(record)
    return checkpoints


def _consolidate_checkpoints(inputs: pd.DataFrame, checkpoint_dir: Path,
                             out: Path, config_hash: str) -> dict:
    checkpoints = _load_checkpoints(inputs, checkpoint_dir, config_hash)
    extractions, errors, attempts, predictions, evidence, statuses = [], [], [], [], [], []
    for checkpoint in checkpoints:
        item_id = checkpoint["argument_pair_id"]
        attempts.extend({"argument_pair_id": item_id, **a} for a in checkpoint["attempts"])
        statuses.append({
            "argument_pair_id": item_id, "status": checkpoint["status"],
            "attempt_count": len(checkpoint["attempts"]),
            "terminal_errors": json.dumps(checkpoint.get("errors", []), ensure_ascii=False),
        })
        if checkpoint["status"] == "valid":
            extractions.append(checkpoint["extraction"])
            predictions.extend(checkpoint["predictions"])
            evidence.append(checkpoint["evidence"])
        else:
            errors.append({
                "argument_pair_id": item_id,
                "errors": checkpoint.get("errors", []),
                "attempt_count": len(checkpoint["attempts"]),
            })
    _atomic_write_text(out / "extractions.jsonl", "".join(
        json.dumps(x, ensure_ascii=False) + "\n" for x in extractions
    ))
    _atomic_write_text(out / "extraction_errors.jsonl", "".join(
        json.dumps(x, ensure_ascii=False) + "\n" for x in errors
    ))
    _atomic_write_text(out / "extraction_attempts.jsonl", "".join(
        json.dumps(x, ensure_ascii=False) + "\n" for x in attempts
    ))
    _atomic_write_csv(pd.DataFrame(predictions, columns=PREDICTION_COLUMNS),
                      out / "proposed_predictions.csv")
    _atomic_write_csv(pd.DataFrame(evidence, columns=EVIDENCE_COLUMNS),
                      out / "item_level_predictions_evidence.csv")
    _atomic_write_csv(pd.DataFrame(statuses, columns=[
        "argument_pair_id", "status", "attempt_count", "terminal_errors",
    ]), out / "item_status.csv")
    return {
        "n_processed": len(checkpoints), "n_valid_extractions": len(extractions),
        "n_invalid_extractions": len(errors), "n_extraction_attempts": len(attempts),
        "n_items_retried": sum(1 for x in checkpoints if len(x["attempts"]) > 1),
    }


def extract_proposed(args: argparse.Namespace) -> None:
    """Run real extraction. This command deliberately has no --gold argument."""
    from llm import EXTRACT_TASK, DEFINITION, extract_pair_with_retry, make_client
    from steering import ProposedScorer

    input_path = Path(args.inputs).resolve()
    inputs = _read_csv(input_path)
    _assert_model_input(inputs)
    if args.expected_items is not None and len(inputs) != args.expected_items:
        raise ValueError(f"Expected {args.expected_items} model inputs, found {len(inputs)}")
    out = Path(args.out).resolve()
    if out.exists() and not args.resume:
        raise SystemExit(f"Output directory already exists (pass --resume to continue): {out}")
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = out / "item_checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    client = make_client(args.model, str(out / "llm_cache.jsonl"))
    max_retries = int(args.max_extraction_retries)
    try:
        implementation_sha = subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        implementation_sha = "unavailable"
    source_files = {
        name: _sha256_file(Path(__file__).with_name(name))
        for name in ("approved_detection_experiment.py", "llm.py", "steering.py")
    }
    input_sha256 = _sha256_file(input_path)
    run_configuration = {
        "model": args.model,
        "model_artifact_digest": args.model_artifact_digest or None,
        "input_sha256": input_sha256,
        "num_ctx": getattr(getattr(client, "inner", None), "num_ctx", None),
        "temperature": 0, "seed": 0, "max_extraction_retries": max_retries,
        "formula": "S(A→B|C) = Temporal × G × U × D",
        "variants": list(ProposedScorer.VARIANTS),
        "definition_sha256": hashlib.sha256(DEFINITION.encode()).hexdigest().upper(),
        "extraction_task_sha256": hashlib.sha256(EXTRACT_TASK.encode()).hexdigest().upper(),
        "source_file_sha256": source_files,
    }
    config_hash = hashlib.sha256(json.dumps(
        run_configuration, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest().upper()
    base_manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "command": " ".join(sys.argv), "python": sys.version,
        "platform": platform.platform(), "implementation_sha": implementation_sha,
        "input_file": str(input_path), "input_sha256": input_sha256,
        "n_inputs": int(len(inputs)), "configuration_sha256": config_hash,
        "run_configuration": run_configuration, "labels_used_as_features": False,
        "gold_argument_spans_used": bool(
            inputs.human_segmentation_used.astype(str).str.upper().eq("TRUE").all()
        ),
        "gold_evidence_spans_used": False,
        "historical_context": "empty: unavailable in approved source",
        "temporal_encoding": "ordinal A=0, B=1 after verified valid_order; not raw timestamps",
        "invalid_extraction_policy": "excluded from predictions and logged; never converted to score zero",
        "checkpoint_policy": "one atomic JSON checkpoint per processed argument_pair_id",
    }
    processed_ids = {
        x["argument_pair_id"] for x in _load_checkpoints(inputs, checkpoint_dir, config_hash)
    }
    for row in inputs.itertuples(index=False):
        item = _edge_item(row)
        if item.item_id in processed_ids:
            print(f"RESUME SKIP {item.item_id}: checkpoint already complete")
            continue
        extraction, attempts = extract_pair_with_retry(
            client, item, "A1", max_retries=max_retries,
        )
        valid = extraction is not None and extraction["validation"]["valid"]
        checkpoint = {
            "argument_pair_id": item.item_id,
            "configuration_sha256": config_hash,
            "completed_at": datetime.now().astimezone().isoformat(),
            "status": "valid" if valid else "invalid",
            "attempts": attempts,
        }
        if valid:
            extraction["argument_pair_id"] = item.item_id
            extraction["source_A_id"] = str(row.A_id)
            extraction["source_B_id"] = str(row.B_id)
            predictions, evidence = _score_extraction(item, row, extraction)
            checkpoint.update({
                "extraction": extraction, "predictions": predictions, "evidence": evidence,
            })
        else:
            checkpoint["errors"] = attempts[-1]["errors"]
        _atomic_write_json(_checkpoint_path(checkpoint_dir, item.item_id), checkpoint)
        progress = _consolidate_checkpoints(inputs, checkpoint_dir, out, config_hash)
        _atomic_write_json(out / "run_manifest.partial.json", {**base_manifest, **progress})
        print(f"CHECKPOINT {item.item_id}: {checkpoint['status']} ({progress['n_processed']}/{len(inputs)})")

    progress = _consolidate_checkpoints(inputs, checkpoint_dir, out, config_hash)
    run_manifest = {**base_manifest, **progress, "completed": progress["n_processed"] == len(inputs)}
    _atomic_write_json(out / "run_manifest.json", run_manifest)
    print(json.dumps(run_manifest, indent=2, ensure_ascii=True))
    print(f"PROPOSED EXTRACTION RESULTS: {out}")


def evaluate_proposed(args: argparse.Namespace) -> None:
    predictions = _read_csv(args.predictions)
    gold = _read_csv(args.gold)
    required = {"argument_pair_id", "input_condition", "method", "score"}
    if required - set(predictions.columns):
        raise ValueError(f"Missing prediction columns: {sorted(required - set(predictions.columns))}")
    if len(gold) != 41 or gold.argument_pair_id.nunique() != 41:
        raise ValueError("Approved binary gold must contain exactly 41 unique argument units")
    if set(gold.label_text) != {"YES", "NO"} or set(gold.label_binary.astype(int)) != {0, 1}:
        raise ValueError("Gold labels must be binary YES/NO")
    if predictions.duplicated(["argument_pair_id", "method"]).any():
        raise ValueError("Duplicate proposed prediction for argument_pair_id/method")
    expected_methods = {"proposed", "proposed_u_only", "proposed_d_only",
                        "proposed_ungated", "proposed_dmean"}
    if set(predictions.method) != expected_methods:
        raise ValueError(f"Unexpected proposed methods: {sorted(set(predictions.method))}")
    predicted_ids = set(predictions.argument_pair_id.astype(str))
    errors = _read_jsonl(args.errors)
    error_ids = {str(record["argument_pair_id"]) for record in errors}
    gold_ids = set(gold.argument_pair_id.astype(str))
    if predicted_ids & error_ids:
        raise ValueError("An argument_pair_id cannot be both predicted and failed")
    if predicted_ids | error_ids != gold_ids:
        missing = sorted(gold_ids - (predicted_ids | error_ids))
        extra = sorted((predicted_ids | error_ids) - gold_ids)
        raise ValueError(f"Prediction/failure coverage mismatch; missing={missing}, extra={extra}")
    attempts = _read_jsonl(args.attempts)
    attempted_ids = {str(record["argument_pair_id"]) for record in attempts}
    if attempted_ids != gold_ids:
        raise ValueError("Attempt audit must cover all 41 gold argument_pair_ids")
    initial_valid_ids = {
        str(record["argument_pair_id"]) for record in attempts
        if int(record["attempt"]) == 1 and bool(record.get("valid"))
    }
    retried_ids = {
        str(record["argument_pair_id"]) for record in attempts
        if int(record["attempt"]) > 1
    }
    metric_table = _metrics(predictions, gold)
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output directory already exists: {out}")
    out.mkdir(parents=True)
    _write_csv(metric_table, out / "proposed_metrics.csv")
    ablations = metric_table.loc[metric_table.method.ne("proposed")].copy()
    ablation_kind = {
        "proposed_u_only": ("remove frame-retention factor D", True),
        "proposed_d_only": ("remove graded uptake strength U_raw; retain evidence gate G", True),
        "proposed_ungated": ("remove evidence gate G and use U_raw", True),
        "proposed_dmean": ("replace min retention with mean retention", False),
    }
    ablations["ablation_description"] = ablations.method.map(
        lambda method: ablation_kind[method][0]
    )
    ablations["independent_component_removal"] = ablations.method.map(
        lambda method: ablation_kind[method][1]
    )
    _write_csv(ablations, out / "ablation_metrics.csv")
    baseline_predictions = _read_csv(args.baseline_predictions)
    baseline_eligible = baseline_predictions.loc[
        baseline_predictions.input_condition.eq("human_segmented")
        & baseline_predictions.argument_pair_id.astype(str).isin(predicted_ids)
    ].copy()
    if set(baseline_eligible.argument_pair_id.astype(str)) != predicted_ids:
        raise ValueError("Baseline predictions do not cover every proposed-method eligible item")
    baseline_human = _metrics(baseline_eligible, gold)
    baseline_human["method_family"] = "non_llm_baseline"
    proposed_comparison = metric_table.copy()
    proposed_comparison["method_family"] = "proposed_or_ablation"
    comparison_columns = [
        "method_family", "input_condition", "method", "n", "n_positive",
        "n_negative", "positive_prevalence", "AUROC", "average_precision",
    ]
    comparison = pd.concat([
        baseline_human[comparison_columns], proposed_comparison[comparison_columns]
    ], ignore_index=True)
    comparison["evaluation_scope"] = "same_post_retry_valid_extractions"
    _write_csv(comparison, out / "baseline_proposed_comparison.csv")
    full_scores = predictions.loc[predictions.method.eq("proposed"), [
        "argument_pair_id", "score", "G", "U", "U_raw", "D", "d_aspect", "d_lens"
    ]].copy()
    item_evaluation = gold.merge(full_scores, on="argument_pair_id", how="left", validate="one_to_one")
    item_evaluation["extraction_status"] = np.where(item_evaluation.score.notna(), "valid", "failed")
    _write_csv(item_evaluation, out / "item_level_evaluation.csv")

    # These are explicitly sensitivity scenarios, never observed proposed predictions.
    sensitivity_rows = []
    for method, group in predictions.groupby("method", sort=True):
        observed = group[["argument_pair_id", "input_condition", "method", "score"]]
        for fill_value, scenario in ((0.0, "all_missing_scores_imputed_0"),
                                     (1.0, "all_missing_scores_imputed_1")):
            complete = gold[["argument_pair_id"]].merge(
                observed, on="argument_pair_id", how="left", validate="one_to_one"
            )
            complete["input_condition"] = "human_segmented"
            complete["method"] = method
            complete["score"] = complete.score.fillna(fill_value)
            record = _metrics(complete, gold).iloc[0].to_dict()
            record.update({
                "scenario": scenario, "imputed_score": fill_value,
                "observed_result": False,
            })
            sensitivity_rows.append(record)
    sensitivity = pd.DataFrame(sensitivity_rows)
    _write_csv(sensitivity, out / "missing_score_sensitivity.csv")

    evidence = _read_csv(args.evidence)
    evidence_ids = set(evidence.argument_pair_id.astype(str))
    if evidence_ids != predicted_ids:
        raise ValueError("Evidence table IDs must equal valid proposed prediction IDs")
    error_analysis = item_evaluation.merge(
        evidence.drop(columns=["input_condition", "status", "score"], errors="ignore"),
        on="argument_pair_id", how="left", validate="one_to_one",
        suffixes=("", "_evidence"),
    )
    # S>0 is the score's pre-existing semantic detection boundary, not a tuned threshold.
    error_analysis["diagnostic_decision_rule"] = "positive iff S > 0; not optimized"
    error_analysis["diagnostic_outcome"] = "terminal_extraction_failure"
    valid_mask = error_analysis.score.notna()
    predicted_positive = error_analysis.score.fillna(0).gt(0)
    positive_gold = error_analysis.label_binary.astype(int).eq(1)
    error_analysis.loc[valid_mask & predicted_positive & positive_gold,
                       "diagnostic_outcome"] = "true_positive"
    error_analysis.loc[valid_mask & predicted_positive & ~positive_gold,
                       "diagnostic_outcome"] = "false_positive"
    error_analysis.loc[valid_mask & ~predicted_positive & positive_gold,
                       "diagnostic_outcome"] = "false_negative"
    error_analysis.loc[valid_mask & ~predicted_positive & ~positive_gold,
                       "diagnostic_outcome"] = "true_negative"
    error_analysis["frame_shift_flag"] = valid_mask & (
        pd.to_numeric(error_analysis.d_aspect, errors="coerce").lt(1)
        | pd.to_numeric(error_analysis.d_lens, errors="coerce").lt(1)
    )
    error_analysis["evidence_gate_failure_flag"] = valid_mask & pd.to_numeric(
        error_analysis.G, errors="coerce"
    ).eq(0)
    _write_csv(error_analysis, out / "error_analysis.csv")
    diagnostic_outcome_counts = error_analysis.diagnostic_outcome.value_counts().to_dict()
    error_frame = pd.DataFrame(errors)
    if error_frame.empty:
        failure_audit = gold.iloc[0:0].copy()
    else:
        error_frame["errors"] = error_frame.errors.map(
            lambda value: json.dumps(value, ensure_ascii=False)
        )
        failure_audit = error_frame.merge(gold, on="argument_pair_id", how="left", validate="one_to_one")
    _write_csv(failure_audit, out / "failure_audit_with_gold.csv")
    coverage = len(predicted_ids) / len(gold)
    initial_coverage = len(initial_valid_ids) / len(gold)
    retry_rate = len(retried_ids) / len(gold)
    terminal_failure_rate = len(error_ids) / len(gold)
    summary = {
        "status": "approved pilot / descriptive only / not held-out",
        "development_overlap_warning": (
            "The five diagnostic development items are included in these 41 approved units; "
            "results are not evidence of held-out generalization."
        ),
        "initial_valid_coverage": initial_coverage,
        "post_retry_coverage": coverage,
        "coverage": coverage,
        "retry_rate": retry_rate,
        "terminal_failure_rate": terminal_failure_rate,
        "n_gold": int(len(gold)),
        "n_scored": len(predicted_ids),
        "n_failed_extractions": len(error_ids),
        "n_attempts": len(attempts),
        "n_initial_valid": len(initial_valid_ids),
        "n_items_retried": len(retried_ids),
        "positive_prevalence_full_gold": float(gold.label_binary.astype(int).mean()),
        "failed_by_gold_label": item_evaluation.loc[
            item_evaluation.extraction_status.eq("failed"), "label_text"
        ].value_counts().to_dict(),
        "diagnostic_outcomes_at_semantic_S_gt_0_rule": diagnostic_outcome_counts,
        "metrics_valid_extractions_only": metric_table.to_dict("records"),
        "warning": (
            "AUROC/AP are complete-case metrics conditional on valid extraction coverage. "
            "Failed extractions are not assigned scores and are not included in these metrics."
        ),
    }
    _write_json(out / "proposed_summary.json", summary)
    main_metric = metric_table.loc[metric_table.method.eq("proposed")].iloc[0]
    lines = [
        "# Experiment 1 — proposed method on approved CMV pilot", "",
        "Scientifically descriptive pilot result only. This is not a held-out test and does not establish generalization.", "",
        "## Data and coverage", "",
        f"- Approved binary argument units: {len(gold)}.",
        f"- Initial-valid coverage: {len(initial_valid_ids)}/{len(gold)} ({initial_coverage:.1%}).",
        f"- Valid proposed scores: {len(predicted_ids)} ({coverage:.1%} coverage).",
        f"- Retry rate: {len(retried_ids)}/{len(gold)} ({retry_rate:.1%}).",
        f"- Terminal extraction failures: {len(error_ids)}; no failed extraction was assigned score zero.",
        f"- Failures by gold label: {summary['failed_by_gold_label']}.",
        f"- Full-gold YES prevalence: {gold.label_binary.astype(int).mean():.3f}.",
        "- Input condition: human-segmented argument units.", "",
        "## Proposed-method complete-case metrics", "",
        "| Method | N scored | AUROC | Average Precision |", "|---|---:|---:|---:|",
    ]
    for record in metric_table.to_dict("records"):
        lines.append(
            f"| {record['method']} | {record['n']} | {record['AUROC']:.3f} | "
            f"{record['average_precision']:.3f} |"
        )
    lines.extend([
        "", "## Baseline comparison on identical eligible items", "",
        "| Family | Method | N | AUROC | Average Precision |",
        "|---|---|---:|---:|---:|",
    ])
    for record in comparison.to_dict("records"):
        lines.append(
            f"| {record['method_family']} | {record['method']} | {record['n']} | "
            f"{record['AUROC']:.3f} | {record['average_precision']:.3f} |"
        )
    lines.extend([
        "", "## Main result", "",
        f"The frozen full score has AUROC {main_metric.AUROC:.3f} and Average Precision "
        f"{main_metric.average_precision:.3f} on {int(main_metric.n)} valid extractions.", "",
        "## Diagnostic error analysis", "",
        f"Using the non-optimized semantic rule S>0, outcome counts are: {diagnostic_outcome_counts}.",
        "See `error_analysis.csv` for FP/FN rows, frame-shift flags, evidence-gate failures and supporting spans.", "",
        "## Interpretation constraints", "",
        "- Metrics are conditional on successful extraction and must always be reported with coverage.",
        "- Baselines in the comparison table are recomputed on exactly the same post-retry valid item IDs.",
        "- Missing-score sensitivity rows impute 0 or 1 only as labeled stress tests; they are not observed results.",
        "- Error-analysis FP/FN uses the semantic diagnostic rule S>0, never a gold-tuned threshold.",
        "- `proposed_d_only` is gated retention (`Temporal * G * D`), not an ungated D-only score.",
        "- `proposed_ungated` removes the explicit G multiplier, but U_raw still comes from the same "
        "validated extraction; under direct-reply inputs and consistency constraints it can be degenerate "
        "with the full score. Treat it as descriptive unless it changes item-level scores.",
        "- `proposed_dmean` is a retention-aggregation sensitivity variant, not an independent component removal.",
        "- The five diagnostic development items are included in the 41 units.",
        "- Human argument segmentation is supplied as model input; this is not raw-comment performance.",
        "- Units from the same thread/comment pair are not statistically independent.",
        "- No threshold was selected on this pilot, and no failed extraction was imputed.",
    ])
    (out / "experiment1_full_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(metric_table.to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--annotations", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=prepare)
    b = sub.add_parser("baselines")
    b.add_argument("--raw-inputs", required=True)
    b.add_argument("--segmented-inputs", required=True)
    b.add_argument("--gold", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(func=baselines)
    e = sub.add_parser("extract-proposed")
    e.add_argument("--inputs", required=True)
    e.add_argument("--model", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--max-extraction-retries", type=int, default=1, choices=(0, 1),
                   help="bounded correction retries after JSON/schema/span validation failure")
    e.add_argument("--expected-items", type=int, default=None,
                   help="fail before inference unless the model input has exactly this many rows")
    e.add_argument("--model-artifact-digest", default="",
                   help="resolved model artifact digest recorded in the run configuration")
    e.add_argument("--resume", action="store_true",
                   help="reuse matching atomic item checkpoints in an existing output directory")
    e.set_defaults(func=extract_proposed)
    v = sub.add_parser("evaluate-proposed")
    v.add_argument("--predictions", required=True)
    v.add_argument("--gold", required=True)
    v.add_argument("--errors", required=True)
    v.add_argument("--attempts", required=True)
    v.add_argument("--evidence", required=True)
    v.add_argument("--baseline-predictions", required=True)
    v.add_argument("--out", required=True)
    v.set_defaults(func=evaluate_proposed)
    return parser


if __name__ == "__main__":
    options = build_parser().parse_args()
    options.func(options)
