"""Real CMV STEP3B *edge-level* baseline diagnostics (not A1/A2 ranking).
Run from repository root:
  python wsdm/evaluate_edge_pilot.py \
    --pairs dataset/pilot/cmv_pilot_50.csv \
    --labels wsdm/pilot/cmv_edge_proposed_review.csv \
    --out wsdm/results_edge_pilot
Requires: pandas numpy scikit-learn.
This is exploratory: pending-review labels are NOT independent gold.
"""
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import roc_auc_score, average_precision_score

def jaccard(a, b):
    aa = set(re.findall(r"\w+", str(a).lower()))
    bb = set(re.findall(r"\w+", str(b).lower()))
    return len(aa & bb) / len(aa | bb) if aa | bb else 0.0

def run(pairs_path, labels_path, out_path):
    pairs = pd.read_csv(pairs_path, keep_default_na=False)
    labels = pd.read_csv(labels_path, keep_default_na=False)
    for name in ["thread_id", "A_id", "B_id", "A_text", "B_text", "temporal_status"]:
        if name not in pairs: raise ValueError("Missing STEP3B column " + name)
    assert pairs.thread_id.nunique() == len(pairs), "Expected 50 unique threads"
    assert pairs.temporal_status.eq("valid_order").all()
    assert not pairs[["A_id", "B_id"]].duplicated().any()
    # Extract primary alignment and match by original source IDs, not by row number.
    primary = labels.loc[labels.alignment_index.astype(str).eq("1")].copy()
    assert not primary[["A_id", "B_id"]].duplicated().any()
    d = pairs.merge(primary[["A_id","B_id","original_pair_id","PROPOSED steering",
                             "AI confidence / review priority","status"]],
                    on=["A_id","B_id"], how="left", validate="one_to_one")
    assert d["PROPOSED steering"].notna().all(), "Unmatched STEP3B pair IDs"
    a, b = d.A_text.astype(str).tolist(), d.B_text.astype(str).tolist()
    n = len(d)
    for name, vec in [
        ("tfidf_word", TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)),
        ("tfidf_char", TfidfVectorizer(analyzer="char",ngram_range=(3,5),sublinear_tf=True)),
    ]:
        x = vec.fit_transform(a+b)
        d[name] = np.asarray(x[:n].multiply(x[n:]).sum(axis=1)).ravel()
    d["token_jaccard"] = [jaccard(x,y) for x,y in zip(a,b)]
    d["reply_structure"] = 1.0  # fixed by direct-reply sampling
    mask = d["PROPOSED steering"].isin(["YES","NO"])
    y = d.loc[mask, "PROPOSED steering"].eq("YES").astype(int)
    assert len(y) and y.nunique()==2, "Binary evaluation requires both labels"
    results = {}
    for col in ["tfidf_word","tfidf_char","token_jaccard","reply_structure"]:
        scores = d.loc[mask,col].to_numpy()
        results[col] = {"AUROC":round(float(roc_auc_score(y,scores)),4),
                        "AP":round(float(average_precision_score(y,scores)),4)}
    summary={"status":"EXPLORATORY / NOT GOLD / NOT RANKING",
             "n_real_pairs":n,"n_threads":int(d.thread_id.nunique()),
             "n_binary":len(y),"labels":d["PROPOSED steering"].value_counts().to_dict(),
             "metrics":results,
             "limitations":[
                "All pairs are direct replies, so reply-only baseline cannot discriminate.",
                "TF-IDF is fitted on the pilot texts; no held-out generalization claims.",
                "The labels are AI-assisted adjudication PROPOSALS, pending human approval.",
                "Arguments within one comment pair are not separately scored.",
                "No A1/A2 ranking labels: cannot run evaluate.py pairwise accuracy."
             ]}
    out=Path(out_path);out.mkdir(parents=True,exist_ok=True)
    d.to_csv(out/"predictions.csv",index=False)
    (out/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--pairs",required=True)
    ap.add_argument("--labels",required=True)
    ap.add_argument("--out",default="wsdm/results_edge_pilot")
    z=ap.parse_args()
    run(z.pairs,z.labels,z.out)
