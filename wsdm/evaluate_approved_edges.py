"""Evaluate approved CMV argumentative-steering annotation units with simple lexical baselines.
Usage (from repository root):
  python wsdm/evaluate_approved_edges.py \
    --labels wsdm/pilot/cmv_adjudicated_pilot_60.csv \
    --out wsdm/results_approved_edges

This is *argument-level*, not the (A1,A2,B) ranking task in evaluate.py.
41 YES/NO arguments are evaluated descriptively; multiple arguments per comment pair
must be grouped by thread in any future train/test split. This script performs no
supervised training or threshold optimization and makes no held-out performance claims.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score


def jaccard(a, b):
    t1, t2 = [set(re.findall(r"\w+", str(t).lower())) for t in (a, b)]
    return len(t1 & t2) / len(t1 | t2) if t1 | t2 else 0.0


def run(args):
    d = pd.read_csv(args.labels, keep_default_na=False, encoding="utf-8-sig")
    required = ["argument_pair_id", "thread_id", "A_id", "B_id", "A_argument_span",
                "B_argument_span", "unit_approved", "review_status", "final_steering"]
    for k in required:
        if k not in d.columns:
            raise ValueError(f"Missing field {k!r}")
    if d.argument_pair_id.duplicated().any():
        raise ValueError("Duplicate argument_pair_id; do not deduplicate by original_pair_id")
    if not d.review_status.eq("APPROVED").all():
        raise ValueError("All rows must be human adjudication APPROVED")
    if not d.unit_approved.isin(["YES", "NO"]).all():
        raise ValueError("Invalid unit_approved values")
    valid = d.unit_approved.eq("YES")
    binary = valid & d.final_steering.isin(["YES", "NO"])
    ambiguous = valid & d.final_steering.eq("UNCLEAR")
    excluded = ~valid
    if (binary | ambiguous | excluded).sum() != len(d):
        raise ValueError("Unexpected label/unit status combination")
    if not d.loc[binary, ["A_argument_span","B_argument_span"]].apply(lambda col: col.str.strip().ne("")).all().all():
        raise ValueError("Some eligible arguments have empty spans")
    test = d.loc[binary].copy()
    y = test.final_steering.eq("YES").astype(int).to_numpy()
    if len(np.unique(y)) != 2:
        raise ValueError("Need positive and negative cases")
    a, b = test.A_argument_span.astype(str).tolist(), test.B_argument_span.astype(str).tolist()
    n = len(test)
    for key, vec in [
        ("tfidf_word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("tfidf_char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True)),
    ]:
        fitted = vec.fit_transform(a + b)  # unsupervised pilot-only vocabulary
        test[key] = np.asarray(fitted[:n].multiply(fitted[n:]).sum(axis=1)).ravel()
    test["token_jaccard"] = [jaccard(x, z) for x, z in zip(a, b)]
    test["reply_only"] = 1.0  # source sample is entirely direct replies
    metrics = {col: {"AUROC": float(roc_auc_score(y, test[col])),
                     "average_precision": float(average_precision_score(y, test[col]))}
               for col in ("tfidf_word","tfidf_char","token_jaccard","reply_only")}
    summary = {
        "task": "binary_argument_relation_diagnostics_NOT_pairwise_ranking",
        "status": "adjudicated pilot / descriptive only / not held-out",
        "n_total_argument_units": int(len(d)),
        "n_valid_argument_units": int(valid.sum()),
        "n_binary": int(binary.sum()),
        "n_unclear_excluded": int(ambiguous.sum()),
        "n_invalid_excluded": int(excluded.sum()),
        "n_distinct_threads_binary": int(test.thread_id.nunique()),
        "n_positive": int(y.sum()), "n_negative": int(n - y.sum()),
        "positive_prevalence": float(y.mean()),
        "metrics": metrics,
        "caveats": ["No held-out test; descriptive pilot only.",
                    "Labels are reviewed AI-assisted annotations, not two independent human annotators.",
                    "Candidate units from the same thread are correlated; no naive independent bootstrap.",
                    "Direct-reply-only structural baseline is constant by sampling design.",
                    "Real G/U/D features must be inferred from text, never copied from gold annotations.",
                    "Does not evaluate the separate ranking item dataset."]
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    test.to_csv(out / "predictions.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--labels", required=True)
    p.add_argument("--out", default="wsdm/results_approved_edges")
    run(p.parse_args())
