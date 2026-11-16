"""evaluate.py -- split by thread and evaluate scorers on pairwise Steering judgments.

  python evaluate.py split --items all.jsonl --out data/ --ratios 0.6,0.2,0.2 --seed 13
  python evaluate.py eval  --items data/test.jsonl --extractions data/extractions_test.jsonl \
      --methods random,cosine,reply_quote,llm,proposed,proposed_u_only,proposed_d_only,proposed_ungated,proposed_dmean \
      --llm-model claude-sonnet-5-5 --cache cache/llm.jsonl --reference cosine --out results/

Metric (doc, section 6): for the same B compare score(A1) vs score(A2) with the independent
human judgment. Items whose gold label is tie/insufficient are excluded from accuracy and
reported as a rate. Predicted ties (e.g. both S=0 because both fail the gate) get 0.5 credit in
`acc` and 0 in `acc_strict`; `coverage` is the share of ordered items with a non-tie prediction.
CIs: bootstrap over THREADS (items of one thread are not independent). No threshold is tuned.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from steering import (
    ORDERED,
    CosineScorer,
    Item,
    ProposedScorer,
    RandomScorer,
    ReplyQuoteScorer,
    Scorer,
    load_extractions,
    load_items,
)

EPS = 1e-9


# ------------------------------------------------------------------------ split
def split_by_thread(items: List[Item], ratios, seed: int) -> Dict[str, List[Item]]:
    threads = sorted({it.thread_id for it in items})
    random.Random(seed).shuffle(threads)
    n = len(threads)
    c1 = int(round(ratios[0] * n))
    c2 = c1 + int(round(ratios[1] * n))
    assign = {t: ("train" if i < c1 else "dev" if i < c2 else "test") for i, t in enumerate(threads)}
    out: Dict[str, List[Item]] = {"train": [], "dev": [], "test": []}
    for it in items:
        out[assign[it.thread_id]].append(it)
    return out


def _item_to_dict(it: Item) -> dict:
    def c(x):
        d = {"id": x.id, "text": x.text, "timestamp": x.timestamp, "parent_id": x.parent_id,
             "quotes": x.quotes}
        if x.hops is not None:
            d["hops"] = x.hops
        return d
    return {"item_id": it.item_id, "thread_id": it.thread_id, "B": c(it.B),
            "candidates": {k: c(v) for k, v in it.candidates.items()}, "label": it.label,
            "slices": it.slices, "context": [c(x) for x in it.context]}


def cmd_split(args) -> None:
    items = load_items(args.items)
    ratios = [float(x) for x in args.ratios.split(",")]
    parts = split_by_thread(items, ratios, args.seed)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    for name, its in parts.items():
        with open(Path(args.out) / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for it in its:
                f.write(json.dumps(_item_to_dict(it), ensure_ascii=False) + "\n")
        print(f"{name}: {len(its)} items, {len({i.thread_id for i in its})} threads")


# ---------------------------------------------------------------------- metrics
def pairwise_credit(label: str, s1: float, s2: float):
    """(credit with tie=0.5, strict credit, decided?) or None if the gold label is not ordered."""
    if label not in ORDERED:
        return None
    if abs(s1 - s2) <= EPS:
        return 0.5, 0.0, False
    pred = "A1>A2" if s1 > s2 else "A1<A2"
    ok = float(pred == label)
    return ok, ok, True


def bootstrap(sums: np.ndarray, counts: np.ndarray, n_boot: int, seed: int) -> np.ndarray:
    """sums: [T, M] credit sums per thread; counts: [T]. Returns [n_boot, M] resampled accuracies."""
    rng = np.random.default_rng(seed)
    T = len(counts)
    idx = rng.integers(0, T, size=(n_boot, T))
    num = sums[idx].sum(axis=1)
    den = counts[idx].sum(axis=1)[:, None]
    return num / np.maximum(den, 1)


def ci(x: np.ndarray, lo: float = 2.5, hi: float = 97.5):
    return float(np.percentile(x, lo)), float(np.percentile(x, hi))


# ------------------------------------------------------------------------- eval
def build_scorer(name: str, args, extractions: Optional[dict]) -> Scorer:
    if name == "random":
        return RandomScorer()
    if name == "cosine":
        return CosineScorer(_embedder(args))
    if name == "reply_quote":
        return ReplyQuoteScorer(_embedder(args))
    if name == "llm":
        from llm import LLMDirectScorer, make_client
        if not args.llm_model:
            raise SystemExit("--llm-model is required for method 'llm'")
        return LLMDirectScorer(make_client(args.llm_model, args.cache))
    if name.startswith("proposed"):
        if extractions is None:
            raise SystemExit("--extractions is required for the proposed methods")
        variant = "full" if name == "proposed" else name.split("_", 1)[1]
        return ProposedScorer(extractions, variant)
    raise SystemExit(f"unknown method {name!r}")


def _embedder(args):
    if getattr(args, "embedder", "tfidf") == "st":
        from steering import SentenceTransformerEmbedder
        return SentenceTransformerEmbedder()
    return None  # default TF-IDF


def cmd_eval(args) -> None:
    items = load_items(args.items)
    fit_items = load_items(args.fit_items) if args.fit_items else items
    extractions = load_extractions(args.extractions) if args.extractions else None
    names = [m.strip() for m in args.methods.split(",") if m.strip()]
    scorers = [build_scorer(m, args, extractions) for m in names]
    for s in scorers:
        s.fit(fit_items)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    threads = sorted({it.thread_id for it in items})
    t_index = {t: i for i, t in enumerate(threads)}
    T, M = len(threads), len(scorers)
    sums = np.zeros((T, M))
    sums_strict = np.zeros((T, M))
    decided = np.zeros((T, M))
    counts = np.zeros(T)
    slice_stats: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    n_ordered = 0
    gold_counts: Dict[str, int] = defaultdict(int)

    with open(out_dir / "predictions.jsonl", "w", encoding="utf-8") as pf:
        for it in items:
            gold_counts[it.label] += 1
            rec = {"item_id": it.item_id, "thread_id": it.thread_id, "label": it.label,
                   "slices": it.slices, "methods": {}}
            ordered = it.label in ORDERED
            if ordered:
                counts[t_index[it.thread_id]] += 1
                n_ordered += 1
            for j, s in enumerate(scorers):
                s1, s2 = s.score(it, "A1"), s.score(it, "A2")
                cr = pairwise_credit(it.label, s1, s2)
                rec["methods"][s.name] = {
                    "s1": s1, "s2": s2,
                    "pred": "tie" if abs(s1 - s2) <= EPS else ("A1>A2" if s1 > s2 else "A1<A2"),
                    "credit": cr[0] if cr else None,
                    "explain_A1": s.explain(it, "A1"), "explain_A2": s.explain(it, "A2")}
                if cr:
                    i = t_index[it.thread_id]
                    sums[i, j] += cr[0]
                    sums_strict[i, j] += cr[1]
                    decided[i, j] += float(cr[2])
                    for tag in it.slices:
                        slice_stats[tag][s.name].append(cr[0])
            pf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if n_ordered == 0:
        raise SystemExit("no items with an ordered gold label (A1>A2 / A1<A2)")
    if T < 20:
        print(f"WARNING: only {T} threads; bootstrap CIs are unreliable.")

    boot = bootstrap(sums, counts, args.boot, args.seed)
    tot = counts.sum()
    ref = names.index(args.reference) if args.reference in names else None

    rows = []
    for j, s in enumerate(scorers):
        lo, hi = ci(boot[:, j])
        row = {"method": s.name, "acc": sums[:, j].sum() / tot, "acc_ci": [lo, hi],
               "acc_strict": sums_strict[:, j].sum() / tot, "coverage": decided[:, j].sum() / tot}
        if ref is not None and j != ref:
            d = boot[:, j] - boot[:, ref]
            row["delta_vs_ref"] = float(sums[:, j].sum() / tot - sums[:, ref].sum() / tot)
            row["delta_ci"] = list(ci(d))
        rows.append(row)

    summary = {"n_items": len(items), "n_threads": T, "n_ordered": n_ordered,
               "gold_label_counts": dict(gold_counts),
               "tie_or_insufficient_rate": (gold_counts["tie"] + gold_counts["insufficient"]) / len(items),
               "reference": args.reference if ref is not None else None, "boot": args.boot,
               "results": rows,
               "slices": {tag: {m: {"acc": float(np.mean(v)), "n": len(v)} for m, v in d.items()}
                          for tag, d in slice_stats.items()}}
    (out_dir / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md = to_markdown(summary, names)
    (out_dir / "results.md").write_text(md, encoding="utf-8")
    write_error_table(out_dir / "errors.jsonl", out_dir / "predictions.jsonl", names)
    print(md)


def to_markdown(sm: dict, names: List[str]) -> str:
    L = [f"items={sm['n_items']}  threads={sm['n_threads']}  ordered={sm['n_ordered']}  "
         f"gold tie/insufficient rate={sm['tie_or_insufficient_rate']:.2f}  gold={sm['gold_label_counts']}", "",
         "| method | acc [95% CI] | acc_strict | coverage | delta vs ref [95% CI] |",
         "|---|---|---|---|---|"]
    for r in sm["results"]:
        d = (f"{r['delta_vs_ref']:+.3f} [{r['delta_ci'][0]:+.3f}, {r['delta_ci'][1]:+.3f}]"
             if "delta_vs_ref" in r else "-")
        L.append(f"| {r['method']} | {r['acc']:.3f} [{r['acc_ci'][0]:.3f}, {r['acc_ci'][1]:.3f}] | "
                 f"{r['acc_strict']:.3f} | {r['coverage']:.2f} | {d} |")
    if sm["slices"]:
        L += ["", "Slices (acc with tie=0.5, n in parentheses):", "",
              "| slice | " + " | ".join(m for m in names) + " |", "|---|" + "---|" * len(names)]
        for tag, d in sorted(sm["slices"].items()):
            cells = [f"{d[m]['acc']:.2f} ({d[m]['n']})" if m in d else "-" for m in
                     [s for s in (r["method"] for r in sm["results"])]]
            L.append(f"| {tag} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def write_error_table(out_path: Path, pred_path: Path, names: List[str]) -> None:
    """One line per wrong (credit<1) ordered item for the proposed method (or first method) -> error analysis."""
    target = "proposed" if "proposed" in names else (names[-1] if names else None)
    n = 0
    with open(pred_path, encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as g:
        for line in f:
            r = json.loads(line)
            m = r["methods"].get(target)
            if m and m["credit"] is not None and m["credit"] < 1.0:
                g.write(json.dumps({"item_id": r["item_id"], "gold": r["label"], "pred": m["pred"],
                                    "s1": m["s1"], "s2": m["s2"], "slices": r["slices"],
                                    "explain_A1": m["explain_A1"], "explain_A2": m["explain_A2"]},
                                   ensure_ascii=False) + "\n")
                n += 1
    print(f"\nerror table ({target}): {n} items -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("split")
    sp.add_argument("--items", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--ratios", default="0.6,0.2,0.2")
    sp.add_argument("--seed", type=int, default=13)
    ev = sub.add_parser("eval")
    ev.add_argument("--items", required=True)
    ev.add_argument("--fit-items", default=None, help="unlabeled-text corpus for TF-IDF (e.g. train.jsonl)")
    ev.add_argument("--extractions", default=None)
    ev.add_argument("--methods", default="random,cosine,reply_quote,proposed")
    ev.add_argument("--reference", default="cosine")
    ev.add_argument("--embedder", choices=["tfidf", "st"], default="tfidf")
    ev.add_argument("--llm-model", default=None)
    ev.add_argument("--cache", default=None)
    ev.add_argument("--boot", type=int, default=2000)
    ev.add_argument("--seed", type=int, default=13)
    ev.add_argument("--out", default="results")
    a = ap.parse_args()
    {"split": cmd_split, "eval": cmd_eval}[a.cmd](a)
