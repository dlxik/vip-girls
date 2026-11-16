"""One-command runner for real CMV baseline and proposed-score diagnostics.

Outputs are inference artifacts for inspection. Unlabeled runs intentionally produce no
accuracy/F1 claims.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from llm import make_client, run_extraction
from steering import (
    CosineScorer,
    ProposedScorer,
    ReplyQuoteScorer,
    load_extractions,
    load_items,
    pair_key,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ITEMS = ROOT / "wsdm" / "pilot" / "items_unlabeled.jsonl"
DEFAULT_RESULTS = ROOT / "wsdm" / "results"
VARIANTS = ("full", "u_only", "d_only", "ungated", "dmean")


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _item_dict(item) -> dict:
    def comment(c, candidate: bool = False):
        row = {
            "id": c.id, "text": c.text, "timestamp": c.timestamp,
            "parent_id": c.parent_id, "quotes": c.quotes,
        }
        if candidate:
            row["hops"] = c.hops
        return row
    return {
        "item_id": item.item_id,
        "thread_id": item.thread_id,
        "B": comment(item.B),
        "candidates": {key: comment(value, True) for key, value in item.candidates.items()},
        "context": [comment(value) for value in item.context],
        "label": item.label,
        "slices": item.slices,
    }


def _validate_items(items) -> list[str]:
    warnings = []
    item_ids = [item.item_id for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("duplicate item_id values")
    pairs = set()
    for item in items:
        if item.label != "unlabeled":
            warnings.append(f"item {item.item_id} has label {item.label!r}; labels are not model inputs")
        for key in ("A1", "A2"):
            a = item.candidates[key]
            if not a.timestamp < item.B.timestamp:
                raise ValueError(f"{item.item_id}/{key}: candidate does not precede B")
        if any(context.timestamp > item.B.timestamp for context in item.context):
            raise ValueError(f"{item.item_id}: future context detected")
        token = (item.B.id, *sorted((item.candidates["A1"].id, item.candidates["A2"].id)))
        if token in pairs:
            raise ValueError(f"duplicate candidate pair: {token}")
        pairs.add(token)
    return warnings


def _predict(items, scorers, extractions) -> list[dict]:
    records = []
    for item in items:
        source = _item_dict(item)
        record = {**source, "methods": {}}
        for scorer in scorers:
            scores = {key: scorer.score(item, key) for key in ("A1", "A2")}
            if abs(scores["A1"] - scores["A2"]) <= 1e-12:
                prediction = "tie"
            else:
                prediction = "A1" if scores["A1"] > scores["A2"] else "A2"
            record["methods"][scorer.name] = {
                "score_A1": scores["A1"],
                "score_A2": scores["A2"],
                "predicted_higher": prediction,
                "explain_A1": scorer.explain(item, "A1"),
                "explain_A2": scorer.explain(item, "A2"),
            }
        records.append(record)
    return records


def _write_csv(path: Path, records: list[dict]) -> None:
    columns = [
        "item_id", "thread_id", "label_status", "slice", "B_id", "A1_id", "A2_id",
        "A1_hops", "A2_hops", "method", "score_A1", "score_A2", "predicted_higher",
        "G_A1", "U_A1", "d_aspect_A1", "d_lens_A1", "G_A2", "U_A2",
        "d_aspect_A2", "d_lens_A2",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            for method, result in record["methods"].items():
                components = []
                for key in ("A1", "A2"):
                    components.append(result[f"explain_{key}"].get("components", {}))
                writer.writerow({
                    "item_id": record["item_id"], "thread_id": record["thread_id"],
                    "label_status": record["label"].upper(),
                    "slice": ";".join(record["slices"]), "B_id": record["B"]["id"],
                    "A1_id": record["candidates"]["A1"]["id"],
                    "A2_id": record["candidates"]["A2"]["id"],
                    "A1_hops": record["candidates"]["A1"].get("hops"),
                    "A2_hops": record["candidates"]["A2"].get("hops"),
                    "method": method, "score_A1": result["score_A1"],
                    "score_A2": result["score_A2"],
                    "predicted_higher": result["predicted_higher"],
                    "G_A1": components[0].get("G"), "U_A1": components[0].get("U_raw"),
                    "d_aspect_A1": components[0].get("d_aspect"),
                    "d_lens_A1": components[0].get("d_lens"),
                    "G_A2": components[1].get("G"), "U_A2": components[1].get("U_raw"),
                    "d_aspect_A2": components[1].get("d_aspect"),
                    "d_lens_A2": components[1].get("d_lens"),
                })


def _summarize(records: list[dict], mode: str, model: str | None, missing_pairs: int) -> dict:
    methods = sorted(records[0]["methods"]) if records else []
    method_summary = {}
    for method in methods:
        values = [record["methods"][method] for record in records]
        method_summary[method] = {
            "prediction_counts": dict(Counter(value["predicted_higher"] for value in values)),
            "mean_score_A1": sum(value["score_A1"] for value in values) / len(values),
            "mean_score_A2": sum(value["score_A2"] for value in values) / len(values),
            "zero_score_items": sum(
                value["score_A1"] == 0 and value["score_A2"] == 0 for value in values
            ),
        }
    disagreements = 0
    if "cosine" in methods and "proposed" in methods:
        disagreements = sum(
            record["methods"]["cosine"]["predicted_higher"]
            != record["methods"]["proposed"]["predicted_higher"]
            for record in records
        )
    return {
        "status": "MOCK / UNLABELED" if model == "mock" else "UNLABELED",
        "scientific_claim": "Inference diagnostics only; no ranking accuracy/F1 without gold labels.",
        "mode": mode, "model": model, "n_items": len(records),
        "n_threads": len({record["thread_id"] for record in records}),
        "methods": methods, "label_counts": dict(Counter(r["label"] for r in records)),
        "missing_extraction_pairs": missing_pairs,
        "baseline_proposed_disagreements": disagreements,
        "method_summary": method_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "proposed"), required=True)
    parser.add_argument("--source", choices=("existing",), default="existing")
    parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    parser.add_argument("--model", help="required for proposed mode: mock, ollama:<name>, or API model")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--out-root", default=str(DEFAULT_RESULTS))
    parser.add_argument("--run-name", default=None)
    args = parser.parse_args()
    if args.mode == "proposed" and not args.model:
        parser.error("--model is required for proposed mode; mock is never selected implicitly")

    items_path = Path(args.items).resolve()
    if not items_path.is_file():
        raise SystemExit(f"items file not found: {items_path}")
    items = load_items(str(items_path), allow_unlabeled=True)
    if args.limit is not None:
        if args.limit <= 0:
            parser.error("--limit must be positive")
        items = items[:args.limit]
    if not items:
        raise SystemExit("no items selected")
    warnings = _validate_items(items)

    run_name = args.run_name or f"{_timestamp()}_{args.mode}_{'mock' if args.model == 'mock' else 'real'}"
    run_dir = Path(args.out_root).resolve() / run_name
    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    selected_path = run_dir / "items.jsonl"
    _write_jsonl(selected_path, (_item_dict(item) for item in items))

    scorers = [CosineScorer(), ReplyQuoteScorer()]
    extraction_map = None
    missing_pairs = 0
    if args.mode == "proposed":
        extraction_path = run_dir / "extractions.jsonl"
        error_path = run_dir / "extraction_errors.jsonl"
        cache_path = run_dir / "llm_cache.jsonl"
        client = make_client(args.model, str(cache_path))
        run_extraction(items, client, str(extraction_path), str(error_path))
        extraction_map = load_extractions(str(extraction_path))
        expected = {
            pair_key(item.candidates[key].id, item.B.id)
            for item in items for key in ("A1", "A2")
        }
        missing_pairs = len(expected - set(extraction_map))
        if missing_pairs:
            warnings.append(f"{missing_pairs} candidate pairs have no valid extraction and score zero")
        scorers.extend(ProposedScorer(extraction_map, variant) for variant in VARIANTS)
    for scorer in scorers:
        scorer.fit(items)

    records = _predict(items, scorers, extraction_map)
    _write_jsonl(run_dir / "predictions.jsonl", records)
    _write_csv(run_dir / "predictions.csv", records)
    summary = _summarize(records, args.mode, args.model, missing_pairs)
    summary["warnings"] = warnings
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "command": " ".join(sys.argv), "python": sys.version,
        "platform": platform.platform(), "mode": args.mode, "source": args.source,
        "source_items": str(items_path), "seed": args.seed, "model": args.model,
        "limit": args.limit, "run_dir": str(run_dir),
        "labels_used_as_features": False,
        "settings": {"tfidf": "dependency-free word TF-IDF", "tie_epsilon": 1e-12,
                     "proposed_variants": list(VARIANTS) if args.mode == "proposed" else []},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"RESULTS SAVED TO: {run_dir}")


if __name__ == "__main__":
    main()
