"""Score real *unlabeled* A1/A2 CMV candidates without gold labels.
This is inference/diagnostics ONLY. It cannot produce accuracy or F1.
Run from wsdm/: python score_unlabeled.py --items pilot/items_unlabeled.jsonl --out results_unlabeled.csv
Optional --extractions path/to/llm-extractions.jsonl enables ProposedScorer.
"""
from __future__ import annotations
import argparse, csv
from pathlib import Path
from steering import load_items, CosineScorer, ReplyQuoteScorer, ProposedScorer, load_extractions

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--items",required=True)
    ap.add_argument("--out",default="results_unlabeled.csv")
    ap.add_argument("--extractions")
    args=ap.parse_args()
    items=load_items(args.items,allow_unlabeled=True)
    scorers=[CosineScorer(),ReplyQuoteScorer()]
    if args.extractions:
        ex=load_extractions(args.extractions)
        scorers.append(ProposedScorer(ex,"full"))
    for scorer in scorers: scorer.fit(items)
    cols=["item_id","thread_id","B_id","A1_id","A2_id","A1_hops","A2_hops",
          "method","score_A1","score_A2","predicted_higher","has_gold"]
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for it in items:
            for scorer in scorers:
                a1,a2=[scorer.score(it,k) for k in ("A1","A2")]
                pred="tie" if abs(a1-a2)<1e-9 else "A1" if a1>a2 else "A2"
                w.writerow({"item_id":it.item_id,"thread_id":it.thread_id,
                    "B_id":it.B.id,"A1_id":it.candidates["A1"].id,
                    "A2_id":it.candidates["A2"].id,
                    "A1_hops":it.candidates["A1"].hops,
                    "A2_hops":it.candidates["A2"].hops,
                    "method":scorer.name,"score_A1":a1,"score_A2":a2,
                    "predicted_higher":pred,"has_gold":"NO"})
    print(f"{len(items)} real unlabeled CMV ranking items; {len(scorers)} methods -> {out}")
    print("WARNING: these are predictions, NOT quality metrics and NOT paper results.")
if __name__=="__main__": main()
