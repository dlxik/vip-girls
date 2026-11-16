"""Exploratory binary detection diagnostics for real direct-reply CMV edges.

This is separate from A1/A2 ranking. It joins by real ``A_id``/``B_id``, preserves
all argument alignments, and does not treat review proposals as gold unless the
caller explicitly requests a provisional diagnostic.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score

BINARY = {"YES", "NO"}
EXCLUDED = {"UNCLEAR", "NOT_APPLICABLE", ""}
APPROVED_STATUSES = {"APPROVED", "FINAL", "GOLD"}


def jaccard(a, b):
    aa = set(re.findall(r"\w+", str(a).lower()))
    bb = set(re.findall(r"\w+", str(b).lower()))
    return len(aa & bb) / len(aa | bb) if aa | bb else 0.0


def _metrics(frame: pd.DataFrame, label_column: str) -> dict:
    mask = frame[label_column].isin(BINARY)
    evaluated = frame.loc[mask].copy()
    result = {
        "n_binary": int(len(evaluated)),
        "class_counts": {
            str(k): int(v) for k, v in evaluated[label_column].value_counts().items()
        },
        "baseline_prevalence": float(evaluated[label_column].eq("YES").mean())
        if len(evaluated) else None,
        "excluded_counts": {
            str(k): int(v) for k, v in frame.loc[~mask, label_column].value_counts().items()
        },
        "metrics": {},
    }
    if len(evaluated) and evaluated[label_column].nunique() == 2:
        y = evaluated[label_column].eq("YES").astype(int)
        for column in ("tfidf_word", "tfidf_char", "token_jaccard", "reply_structure"):
            scores = evaluated[column].to_numpy()
            result["metrics"][column] = {
                "AUROC": round(float(roc_auc_score(y, scores)), 4),
                "Average Precision": round(float(average_precision_score(y, scores)), 4),
            }
    else:
        result["metric_warning"] = "AUROC/AP require at least one YES and one NO label"
    return result


def _comment_label(values: pd.Series) -> str:
    labels = set(values) & BINARY
    if "YES" in labels:
        return "YES"
    if labels == {"NO"}:
        return "NO"
    return "EXCLUDED"


def run(pairs_path, labels_path, out_path, use_provisional=False):
    pairs = pd.read_csv(pairs_path, keep_default_na=False)
    labels = pd.read_csv(labels_path, keep_default_na=False)
    for name in ["thread_id", "A_id", "B_id", "A_text", "B_text", "temporal_status"]:
        if name not in pairs:
            raise ValueError("Missing STEP3B column " + name)
    for name in [
        "argument_pair_id", "original_pair_id", "alignment_index", "A_id", "B_id",
        "PROPOSED steering", "status", "human final label",
    ]:
        if name not in labels:
            raise ValueError("Missing annotation column " + name)
    if pairs[["A_id", "B_id"]].duplicated().any():
        raise ValueError("STEP3B pairs must be unique by A_id/B_id")
    if labels["argument_pair_id"].duplicated().any():
        raise ValueError("argument_pair_id must be unique")
    if not pairs["temporal_status"].eq("valid_order").all():
        raise ValueError("all evaluated pairs must have temporal_status=valid_order")

    argument = pairs.merge(
        labels, on=["A_id", "B_id"], how="left", validate="one_to_many",
        suffixes=("_pair", "_annotation"),
    )
    if argument["argument_pair_id"].eq("").any() or argument["argument_pair_id"].isna().any():
        raise ValueError("unmatched STEP3B A_id/B_id values")
    if len(argument) != len(labels):
        unmatched = labels.merge(
            pairs[["A_id", "B_id"]], on=["A_id", "B_id"], how="left", indicator=True
        )
        raise ValueError(
            f"annotation rows did not join one-to-many: joined={len(argument)}, "
            f"labels={len(labels)}, unmatched={int(unmatched['_merge'].ne('both').sum())}"
        )

    a, b = pairs.A_text.astype(str).tolist(), pairs.B_text.astype(str).tolist()
    n = len(pairs)
    feature_frame = pairs[["A_id", "B_id"]].copy()
    for name, vectorizer in [
        ("tfidf_word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("tfidf_char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True)),
    ]:
        matrix = vectorizer.fit_transform(a + b)
        feature_frame[name] = np.asarray(matrix[:n].multiply(matrix[n:]).sum(axis=1)).ravel()
    feature_frame["token_jaccard"] = [jaccard(x, y) for x, y in zip(a, b)]
    feature_frame["reply_structure"] = 1.0
    argument = argument.merge(feature_frame, on=["A_id", "B_id"], validate="many_to_one")

    statuses = argument["status"].astype(str).str.upper().str.strip()
    final = argument["human final label"].astype(str).str.upper().str.strip()
    approved = statuses.isin(APPROVED_STATUSES) & final.isin(BINARY | EXCLUDED)
    argument["evaluation_label"] = np.where(approved, final, "")
    label_source = "approved human final label"
    evaluation_status = "GOLD" if approved.any() else "NO APPROVED GOLD"
    if use_provisional:
        argument["evaluation_label"] = (
            argument["PROPOSED steering"].astype(str).str.upper().str.strip()
        )
        label_source = "PROVISIONAL AI-assisted review proposal"
        evaluation_status = "PROVISIONAL / NOT GOLD"

    comment_labels = (
        argument.groupby(["A_id", "B_id"])["evaluation_label"]
        .apply(_comment_label).rename("evaluation_label").reset_index()
    )
    comment = feature_frame.merge(comment_labels, on=["A_id", "B_id"], validate="one_to_one")
    summary = {
        "status": f"EXPLORATORY / {evaluation_status} / NOT RANKING",
        "label_source": label_source,
        "n_real_comment_pairs": int(len(pairs)),
        "n_threads": int(pairs.thread_id.nunique()),
        "n_argument_alignments": int(len(argument)),
        "argument_level": _metrics(argument, "evaluation_label"),
        "comment_level": _metrics(comment, "evaluation_label"),
        "comment_label_rule": "YES if any aligned argument is YES; NO if binary alignments are all NO",
        "limitations": [
            "All pairs are direct replies, so reply-only is constant and cannot discriminate.",
            "TF-IDF is fitted on pilot texts; no held-out generalization claim is supported.",
            "Argument-level rows from the same comment pair share the same baseline text score.",
            "UNCLEAR and NOT_APPLICABLE are excluded from binary metrics.",
            "This dataset has no A1/A2 comparative labels and cannot establish ranking accuracy.",
        ],
    }
    if use_provisional:
        summary["limitations"].insert(
            0, "AI-assisted adjudication proposals are diagnostic labels, not definitive gold."
        )
    out = Path(out_path)
    out.mkdir(parents=True, exist_ok=True)
    argument.to_csv(out / "predictions_argument_level.csv", index=False)
    comment.to_csv(out / "predictions_comment_level.csv", index=False)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"RESULTS SAVED TO: {out.resolve()}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", default="wsdm/results/edge_pilot")
    parser.add_argument(
        "--use-provisional", action="store_true",
        help="explicitly evaluate PROPOSED steering as PROVISIONAL / NOT GOLD",
    )
    args = parser.parse_args()
    run(args.pairs, args.labels, args.out, args.use_provisional)
