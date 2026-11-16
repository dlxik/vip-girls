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


def extract_proposed(args: argparse.Namespace) -> None:
    """Run real extraction.  This command deliberately has no --gold argument."""
    from llm import extract_pair, make_client
    from steering import ProposedScorer, pair_key

    inputs = _read_csv(args.inputs)
    _assert_model_input(inputs)
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output directory already exists: {out}")
    out.mkdir(parents=True)
    client = make_client(args.model, str(out / "llm_cache.jsonl"))
    valid_extractions = []
    errors = []
    predictions = []
    for row in inputs.itertuples(index=False):
        item = _edge_item(row)
        extraction = extract_pair(client, item, "A1")
        if extraction is None:
            errors.append({"argument_pair_id": item.item_id,
                           "errors": ["unparseable JSON"]})
            continue
        if not extraction["validation"]["valid"]:
            errors.append({"argument_pair_id": item.item_id,
                           "errors": extraction["validation"]["errors"]})
            continue
        extraction["argument_pair_id"] = item.item_id
        extraction["source_A_id"] = str(row.A_id)
        extraction["source_B_id"] = str(row.B_id)
        valid_extractions.append(extraction)
        mapping = {pair_key(item.candidates["A1"].id, item.B.id): extraction}
        for variant in ProposedScorer.VARIANTS:
            scorer = ProposedScorer(mapping, variant)
            score = scorer.score(item, "A1")
            explanation = scorer.explain(item, "A1")
            component = explanation["components"]
            predictions.append({
                "argument_pair_id": item.item_id,
                "input_condition": str(row.input_condition),
                "method": scorer.name,
                "score": score,
                "Temporal": int(component["time_ok"]),
                "G": component["G"], "U": component["U"],
                "U_raw": component["U_raw"], "D": component["D"],
                "d_aspect": component["d_aspect"], "d_lens": component["d_lens"],
            })

    with (out / "extractions.jsonl").open("w", encoding="utf-8") as handle:
        for record in valid_extractions:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (out / "extraction_errors.jsonl").open("w", encoding="utf-8") as handle:
        for record in errors:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    _write_csv(pd.DataFrame(predictions), out / "proposed_predictions.csv")
    run_manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "command": " ".join(sys.argv), "python": sys.version,
        "platform": platform.platform(), "model": args.model,
        "input_file": str(Path(args.inputs).resolve()),
        "n_inputs": int(len(inputs)), "n_valid_extractions": len(valid_extractions),
        "n_invalid_extractions": len(errors),
        "labels_used_as_features": False,
        "gold_argument_spans_used": bool(inputs.human_segmentation_used.astype(str).str.upper().eq("TRUE").all()),
        "gold_evidence_spans_used": False,
        "historical_context": "empty: unavailable in approved source",
        "temporal_encoding": "ordinal A=0, B=1 after verified valid_order; not raw timestamps",
        "formula": "S(A→B|C) = Temporal × G × U × D",
        "invalid_extraction_policy": "excluded from predictions and logged; never converted to score zero",
    }
    _write_json(out / "run_manifest.json", run_manifest)
    print(json.dumps(run_manifest, indent=2, ensure_ascii=False))
    print(f"PROPOSED EXTRACTION RESULTS: {out}")


def evaluate_proposed(args: argparse.Namespace) -> None:
    predictions = _read_csv(args.predictions)
    gold = _read_csv(args.gold)
    required = {"argument_pair_id", "input_condition", "method", "score"}
    if required - set(predictions.columns):
        raise ValueError(f"Missing prediction columns: {sorted(required - set(predictions.columns))}")
    metric_table = _metrics(predictions, gold)
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output directory already exists: {out}")
    out.mkdir(parents=True)
    _write_csv(metric_table, out / "proposed_metrics.csv")
    coverage = predictions.argument_pair_id.nunique() / len(gold)
    _write_json(out / "proposed_summary.json", {
        "status": "approved pilot / descriptive only / not held-out",
        "coverage": coverage,
        "n_gold": int(len(gold)),
        "n_scored": int(predictions.argument_pair_id.nunique()),
        "metrics_valid_extractions_only": metric_table.to_dict("records"),
        "warning": "Metrics are conditional on valid extraction coverage; report coverage beside metrics.",
    })
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
    e.set_defaults(func=extract_proposed)
    v = sub.add_parser("evaluate-proposed")
    v.add_argument("--predictions", required=True)
    v.add_argument("--gold", required=True)
    v.add_argument("--out", required=True)
    v.set_defaults(func=evaluate_proposed)
    return parser


if __name__ == "__main__":
    options = build_parser().parse_args()
    options.func(options)
