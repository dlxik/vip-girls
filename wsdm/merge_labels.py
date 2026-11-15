"""merge_labels.py -- agreement between two annotators, adjudication sheet, final labelled items.

Label codes to type in the `label` column of the sheets:
   1 = A1 steers B more      2 = A2 steers B more
   t = tie (both steer B equally)      i = insufficient (neither / not enough evidence)

  python merge_labels.py kappa    --sheet1 pilot/annotator1.csv --sheet2 pilot/annotator2.csv --out pilot/disagreements.csv
  (fill the `final` column of disagreements.csv together)
  python merge_labels.py finalize --items pilot/items_unlabeled.jsonl --sheet1 ... --sheet2 ... \
                                  --disagreements pilot/disagreements.csv --out pilot/labeled.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

CODE = {"1": "A1>A2", "2": "A1<A2", "t": "tie", "i": "insufficient",
        "a1": "A1>A2", "a2": "A1<A2", "tie": "tie", "insufficient": "insufficient"}
CATS = ["A1>A2", "A1<A2", "tie", "insufficient"]


def norm(x: Optional[str]) -> Optional[str]:
    return CODE.get((x or "").strip().lower())


def read_sheet(path: str) -> Dict[str, dict]:
    """Reads a CSV saved by Excel; auto-detects , ; or tab (Excel on some locales saves with ';')."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        header = f.readline()
        f.seek(0)
        delim = max(",;\t", key=header.count)
        return {r["item_id"]: r for r in csv.DictReader(f, delimiter=delim)}


def cohen_kappa(a: List[str], b: List[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in CATS)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def kappa_ci(a, b, n_boot=1000, seed=13):
    rng, n, ks = random.Random(seed), len(a), []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        ks.append(cohen_kappa([a[i] for i in idx], [b[i] for i in idx]))
    ks.sort()
    return ks[int(0.025 * n_boot)], ks[int(0.975 * n_boot)]


def cmd_kappa(args) -> None:
    s1, s2 = read_sheet(args.sheet1), read_sheet(args.sheet2)
    if set(s1) != set(s2):
        raise SystemExit("the two sheets do not contain the same item_ids")
    ids = sorted(s1)
    bad = [i for i in ids if norm(s1[i]["label"]) is None or norm(s2[i]["label"]) is None]
    if bad:
        raise SystemExit(f"{len(bad)} rows have an empty/invalid label (use 1/2/t/i), e.g. {bad[:5]}")
    a, b = [norm(s1[i]["label"]) for i in ids], [norm(s2[i]["label"]) for i in ids]
    n = len(ids)
    agree = sum(x == y for x, y in zip(a, b)) / n
    k = cohen_kappa(a, b)
    lo, hi = kappa_ci(a, b)
    both_ord = [(x, y) for x, y in zip(a, b) if x in ("A1>A2", "A1<A2") and y in ("A1>A2", "A1<A2")]
    ord_agree = sum(x == y for x, y in both_ord) / len(both_ord) if both_ord else float("nan")
    print(f"items: {n}")
    print(f"raw agreement (4 classes): {agree:.3f}")
    print(f"Cohen's kappa (4 classes): {k:.3f}   bootstrap 95% CI [{lo:.3f}, {hi:.3f}]  (wide when n is small)")
    print(f"both gave an ordered label: {len(both_ord)} items; same direction: {ord_agree:.3f}")
    print("label counts annotator1:", dict(Counter(a)))
    print("label counts annotator2:", dict(Counter(b)))
    print("confusion (rows = annotator1, cols = annotator2):")
    print("            " + "  ".join(f"{c:>12}" for c in CATS))
    for r in CATS:
        print(f"{r:>12}  " + "  ".join(f"{sum(1 for x, y in zip(a, b) if x == r and y == c):>12}" for c in CATS))
    dis = [i for i, x, y in zip(ids, a, b) if x != y]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        cols = ["item_id", "label_1", "label_2", "final", "B_text", "A1_text", "A1_relation",
                "A2_text", "A2_relation"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i in dis:
            r = s1[i]
            w.writerow({"item_id": i, "label_1": norm(s1[i]["label"]), "label_2": norm(s2[i]["label"]),
                        "final": "", "B_text": r["B_text"], "A1_text": r["A1_text"],
                        "A1_relation": r["A1_relation"], "A2_text": r["A2_text"], "A2_relation": r["A2_relation"]})
    print(f"\n{len(dis)} disagreements -> {args.out} (fill `final` with 1/2/t/i after discussion)")


def _tags(*rows) -> List[str]:
    out = []
    for r in rows:
        for t in (r.get("tags") or "").replace(";", ",").split(","):
            t = t.strip().lower().replace(" ", "_")
            if t and t not in out:
                out.append(t)
    return out


def cmd_finalize(args) -> None:
    s1, s2 = read_sheet(args.sheet1), read_sheet(args.sheet2)
    final: Dict[str, str] = {}
    if args.disagreements and Path(args.disagreements).exists():
        for iid, r in read_sheet(args.disagreements).items():
            v = norm(r.get("final"))
            if v:
                final[iid] = v
    kept, dropped, counts = [], [], Counter()
    with open(args.items, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            it = json.loads(line)
            i = it["item_id"]
            l1, l2 = norm(s1[i]["label"]), norm(s2[i]["label"])
            lab = l1 if (l1 and l1 == l2) else final.get(i)
            if lab is None:
                dropped.append(i)
                continue
            it["label"] = lab
            it["slices"] = list(dict.fromkeys(it.get("slices", []) + _tags(s1[i], s2[i])))
            counts[lab] += 1
            kept.append(it)
    with open(args.out, "w", encoding="utf-8") as g:
        g.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in kept)
    print(f"kept {len(kept)} items -> {args.out}; label counts: {dict(counts)}")
    if dropped:
        print(f"dropped {len(dropped)} items without an agreed or adjudicated label: {dropped[:5]}...")
    print(f"ordered (usable for accuracy): {counts['A1>A2'] + counts['A1<A2']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kappa")
    k.add_argument("--sheet1", required=True)
    k.add_argument("--sheet2", required=True)
    k.add_argument("--out", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--items", required=True)
    f.add_argument("--sheet1", required=True)
    f.add_argument("--sheet2", required=True)
    f.add_argument("--disagreements", default=None)
    f.add_argument("--out", required=True)
    a = ap.parse_args()
    {"kappa": cmd_kappa, "finalize": cmd_finalize}[a.cmd](a)
