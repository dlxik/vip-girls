"""Build unlabeled A1/A2 ranking items from Person B's canonical CMV Parquet tables.

This adapter preserves source IDs, uses only observed timestamps, validates reply edges,
and delegates candidate construction/hard-negative sampling to ``build_items.py``.
It never interprets a reply edge as argumentative support or attack.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd
from build_items import build_items_from_threads

UTTERANCE_COLUMNS = {
    "utterance_id", "thread_id", "parent_id", "speaker", "text", "timestamp",
    "text_status", "timestamp_status",
}
EDGE_COLUMNS = {
    "parent_id", "child_id", "thread_id", "parent_exists", "temporal_status",
}


def _require_columns(frame: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path}: missing required columns: {missing}")


def _read_sources(utterances_path: Path, edges_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not utterances_path.is_file():
        raise FileNotFoundError(f"canonical utterances file not found: {utterances_path}")
    if not edges_path.is_file():
        raise FileNotFoundError(f"canonical reply-edge file not found: {edges_path}")
    utterances = pd.read_parquet(
        utterances_path,
        columns=sorted(UTTERANCE_COLUMNS),
    )
    edges = pd.read_parquet(edges_path, columns=sorted(EDGE_COLUMNS))
    _require_columns(utterances, UTTERANCE_COLUMNS, utterances_path)
    _require_columns(edges, EDGE_COLUMNS, edges_path)
    if utterances["utterance_id"].duplicated().any():
        raise ValueError("canonical utterance_id values are not unique")
    if edges["child_id"].duplicated().any():
        raise ValueError("canonical reply edges contain duplicate child_id values")
    return utterances, edges


def _validated_threads(utterances: pd.DataFrame, edges: pd.DataFrame) -> Dict[str, List[dict]]:
    """Return build_items-compatible rows after validating the canonical graph.

    Missing timestamps remain missing. ``build_items_from_threads`` is called in strict
    mode so such rows participate only in the parent map and are never candidates/context.
    """
    edge_lookup = edges.set_index("child_id", drop=False)
    non_roots = utterances.loc[utterances["parent_id"].notna()]
    missing_edges = sorted(set(non_roots["utterance_id"]) - set(edges["child_id"]))
    if missing_edges:
        raise ValueError(f"{len(missing_edges)} non-root utterances have no reply edge")

    mismatches = []
    for row in non_roots[["utterance_id", "parent_id", "thread_id"]].itertuples(index=False):
        edge = edge_lookup.loc[row.utterance_id]
        if str(edge.parent_id) != str(row.parent_id) or str(edge.thread_id) != str(row.thread_id):
            mismatches.append(row.utterance_id)
            if len(mismatches) >= 10:
                break
    if mismatches:
        raise ValueError(f"reply-edge/utterance mismatch for child IDs: {mismatches}")

    threads: Dict[str, List[dict]] = defaultdict(list)
    for row in utterances.itertuples(index=False):
        timestamp = None if pd.isna(row.timestamp) else float(row.timestamp)
        parent = None if pd.isna(row.parent_id) else str(row.parent_id)
        text = None if pd.isna(row.text) else str(row.text)
        threads[str(row.thread_id)].append({
            "id": str(row.utterance_id),
            "text": text,
            "timestamp": timestamp,
            "reply_to": parent,
            "speaker": "" if pd.isna(row.speaker) else str(row.speaker),
        })
    return threads


def _pair_token(item: dict) -> str:
    ids = sorted((str(item["candidates"]["A1"]["id"]), str(item["candidates"]["A2"]["id"])))
    return f"{item['B']['id']}|{ids[0]}|{ids[1]}"


def validate_items(items: Iterable[dict]) -> dict:
    items = list(items)
    item_ids, pairs = set(), set()
    errors = []
    for item in items:
        if item["item_id"] in item_ids:
            errors.append(f"duplicate item_id {item['item_id']}")
        item_ids.add(item["item_id"])
        token = _pair_token(item)
        if token in pairs:
            errors.append(f"duplicate candidate pair {token}")
        pairs.add(token)
        b_time = item["B"].get("timestamp")
        if b_time is None:
            errors.append(f"{item['item_id']}: B timestamp is missing")
        for key in ("A1", "A2"):
            candidate = item["candidates"][key]
            if candidate.get("timestamp") is None:
                errors.append(f"{item['item_id']}/{key}: timestamp is missing")
            elif b_time is not None and not candidate["timestamp"] < b_time:
                errors.append(f"{item['item_id']}/{key}: temporal precedence violated")
        for context in item.get("context", []):
            if context.get("timestamp") is None or context["timestamp"] > b_time:
                errors.append(f"{item['item_id']}: invalid/future context {context.get('id')}")
    if errors:
        raise ValueError("item validation failed:\n" + "\n".join(errors[:20]))
    return {
        "n_items": len(items),
        "n_threads": len({item["thread_id"] for item in items}),
        "duplicate_item_ids": 0,
        "duplicate_candidate_pairs": 0,
        "temporal_violations": 0,
        "missing_timestamps": 0,
        "future_context_records": 0,
    }


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_thread_splits(items: List[dict], out_dir: Path, seed: int) -> dict:
    threads = sorted({item["thread_id"] for item in items})
    random.Random(seed).shuffle(threads)
    n = len(threads)
    cut_train, cut_dev = round(0.7 * n), round(0.85 * n)
    membership = {
        **{thread: "train" for thread in threads[:cut_train]},
        **{thread: "dev" for thread in threads[cut_train:cut_dev]},
        **{thread: "test" for thread in threads[cut_dev:]},
    }
    counts = {}
    for split in ("train", "dev", "test"):
        rows = [item for item in items if membership[item["thread_id"]] == split]
        _write_jsonl(out_dir / "split" / f"{split}.jsonl", rows)
        counts[split] = {"items": len(rows), "threads": len({r["thread_id"] for r in rows})}
    return counts


def build(args: argparse.Namespace) -> tuple[Path, dict]:
    utterances_path = Path(args.utterances).resolve()
    edges_path = Path(args.edges).resolve()
    utterances, edges = _read_sources(utterances_path, edges_path)
    threads = _validated_threads(utterances, edges)
    items = build_items_from_threads(
        threads,
        n=args.n,
        seed=args.seed,
        max_per_thread=args.max_per_thread,
        min_words=args.min_words,
        min_words_b=args.min_words_b,
        max_words=args.max_words,
        sample_threads=args.sample_threads,
        impute_root_timestamps=False,
    )
    if len(items) != args.n:
        raise RuntimeError(f"requested {args.n} items but only constructed {len(items)}")
    for item in items:
        for key in ("A1", "A2"):
            item["candidates"][key].setdefault("hops", None)
        item["source"] = {
            "dataset": "ConvoKit winning-args-corpus via Person B canonical tables",
            "utterances_parquet": str(utterances_path),
            "reply_edges_parquet": str(edges_path),
            "sampling_seed": args.seed,
            "candidate_policy": item["slices"][0] if item.get("slices") else None,
            "reply_edges_are_argument_labels": False,
        }
    summary = validate_items(items)
    summary["seed"] = args.seed
    summary["source_fingerprint"] = hashlib.sha256(
        f"{utterances_path}|{utterances_path.stat().st_size}|{edges_path}|{edges_path.stat().st_size}".encode()
    ).hexdigest()
    out = Path(args.out)
    _write_jsonl(out, items)
    summary["splits"] = _write_thread_splits(items, out.parent, args.seed)
    summary_path = out.parent / "build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return out, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--utterances", required=True)
    parser.add_argument("--edges", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--max-per-thread", type=int, default=2)
    parser.add_argument("--min-words", type=int, default=12)
    parser.add_argument("--min-words-b", type=int, default=8)
    parser.add_argument("--max-words", type=int, default=350)
    parser.add_argument("--sample-threads", type=int, default=400)
    args = parser.parse_args()
    out, summary = build(args)
    print(json.dumps(summary, indent=2))
    print(f"items saved to: {out.resolve()}")


if __name__ == "__main__":
    main()
