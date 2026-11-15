"""build_items.py -- ChangeMyView (ConvoKit "winning-args-corpus") -> pairwise items + annotation sheets.

  python build_items.py inspect --n 2
  python build_items.py build --n 50 --out pilot --seed 13
  python build_items.py build --n 100 --out test --seed 29 --exclude pilot/items_unlabeled.jsonl

Outputs in --out: items_unlabeled.jsonl (label = "unlabeled"), sheet_annotator1.csv, sheet_annotator2.csv.

Pair types (all structural, so they exist before any human label):
  parent_vs_other     : direct parent  vs  a high-similarity comment from ANOTHER branch
  parent_vs_ancestor  : direct parent  vs  an ancestor >= 2 reply steps up
  ancestor_vs_other   : ancestor >= 2  vs  a high-similarity comment from another branch
Candidate order (A1/A2) is randomised. CMV's `delta` / `success` metadata is never read.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from steering import Comment, TfidfEmbedder, compute_hops, quote_match, tokenize

BOTS = {"deltabot", "automoderator", "[deleted]"}
TYPES = ("parent_vs_other", "parent_vs_ancestor", "ancestor_vs_other")
URL_RE = re.compile(r"https?://\S+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")             # [text](url) -> text
# delta marks are persuasion signals, not steering evidence: strip them so annotators/LLM are not cued by them
DELTA_RE = re.compile(r"&#(?:8710|916);|&#x(?:2206|394);|[\u2206\u0394]|!delta", re.I)
CHATTER_RE = re.compile(r"delta\s?bot|!delta", re.I)                # comments about the delta system itself


# ------------------------------------------------------------------ text cleaning
def clean(raw: Optional[str]):
    """HTML-unescape, move markdown quote lines ('> ...') into `quotes`, return (body, quotes)."""
    text = html.unescape(raw or "")
    text = DELTA_RE.sub("", text)
    text = MD_LINK_RE.sub(r"\1", text)
    body: List[str] = []
    quotes: List[str] = []
    cur: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            q = s.lstrip("> ").strip()
            if q:
                cur.append(q)
        else:
            if cur:
                quotes.append(" ".join(cur))
                cur = []
            body.append(line)
    if cur:
        quotes.append(" ".join(cur))
    body_text = re.sub(r"\s+", " ", URL_RE.sub("", " ".join(body))).strip()
    return body_text, quotes


# --------------------------------------------------------------------- core logic
def prep_thread(utts: List[dict], min_words: int, min_words_b: int, max_words: int):
    """Returns (parent map over ALL utterances, valid comments, all usable comments, speakers).
    valid = usable AND within the word limits (candidates / B); all = usable only (used for context).
    Filtered comments still count as reply steps. CMV's OP has no timestamp: it is given a time
    just before the earliest reply (it precedes every reply by construction)."""
    parent_of = {u["id"]: u.get("reply_to") for u in utts}
    known = [u["timestamp"] for u in utts if u.get("timestamp") is not None]
    floor = (min(known) - 1) if known else 0
    valid: Dict[str, Comment] = {}
    allc: Dict[str, Comment] = {}
    speaker: Dict[str, str] = {}
    for u in utts:
        t = u.get("timestamp")
        if t is None:
            if u.get("reply_to") is not None:
                continue
            t = floor
        spk = str(u.get("speaker") or "").lower()
        if spk in BOTS:
            continue
        raw = u.get("text") or ""
        if CHATTER_RE.search(raw):
            continue
        text, quotes = clean(raw)
        if text.lower() in {"[deleted]", "[removed]", ""}:
            continue
        c = Comment(id=u["id"], text=text, timestamp=float(t), parent_id=u.get("reply_to"), quotes=quotes)
        allc[u["id"]] = c
        speaker[u["id"]] = spk
        if min(min_words, min_words_b) <= len(tokenize(text)) <= max_words:
            valid[u["id"]] = c
    return parent_of, valid, allc, speaker


def _dot(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def build_items_from_threads(threads: Dict[str, List[dict]], n: int, seed: int = 13,
                             max_per_thread: int = 2, min_words: int = 12, min_words_b: int = 8,
                             max_words: int = 350, sample_threads: int = 400,
                             exclude_threads=frozenset()) -> List[dict]:
    rng = random.Random(seed)
    tids = sorted(t for t in threads if t not in exclude_threads)
    rng.shuffle(tids)
    tids = tids[:sample_threads]
    prepped = {t: prep_thread(threads[t], min_words, min_words_b, max_words) for t in tids}

    emb = TfidfEmbedder().fit(c.text for _, valid, _, _ in prepped.values() for c in valid.values())
    vec_cache: Dict[str, dict] = {}

    def vec(c: Comment) -> dict:
        if c.id not in vec_cache:
            vec_cache[c.id] = emb._vec(c.text)
        return vec_cache[c.id]

    items: List[dict] = []
    type_count: Counter = Counter()
    for tid in tids:
        if len(items) >= n:
            break
        parent_of, valid, allc, speaker = prepped[tid]
        bs = [c for c in valid.values() if parent_of.get(c.id) is not None and
              len(tokenize(c.text)) >= min_words_b]
        rng.shuffle(bs)
        made = 0
        for b in bs:
            if made >= max_per_thread or len(items) >= n:
                break
            # ancestors (raw chain, so hops match compute_hops on the full reply tree)
            chain, cur, seen = [], parent_of.get(b.id), set()
            while cur is not None and cur not in seen:
                seen.add(cur)
                chain.append(cur)
                cur = parent_of.get(cur)
            anc = [(valid[a], compute_hops(parent_of, a, b.id)) for a in chain
                   if a in valid and len(tokenize(valid[a].text)) >= min_words]
            parent = next((c for c, h in anc if h == 1), None)
            anc2 = sorted([(c, h) for c, h in anc if h and h >= 2], key=lambda x: -_dot(vec(x[0]), vec(b)))
            chain_set = set(chain)
            others = sorted(
                [c for c in valid.values() if c.id != b.id and c.id not in chain_set and
                 c.timestamp < b.timestamp and speaker[c.id] != speaker[b.id] and
                 len(tokenize(c.text)) >= min_words],
                key=lambda c: -_dot(vec(c), vec(b)))
            other = others[0] if others else None
            options = {}
            if parent and other:
                options["parent_vs_other"] = ((parent, 1), (other, None))
            if parent and anc2:
                options["parent_vs_ancestor"] = ((parent, 1), anc2[0])
            if anc2 and other:
                options["ancestor_vs_other"] = (anc2[0], (other, None))
            options = {k: v for k, v in options.items()
                       if all(c.timestamp < b.timestamp for c, _ in v)}
            if not options:
                continue
            t = min(options, key=lambda k: (type_count[k], rng.random()))
            pair = list(options[t])
            rng.shuffle(pair)
            slices = [t]
            for c, h in pair:
                if quote_match(c, b):
                    slices.append("quote_direct" if h == 1 else "quote_indirect" if h else "quote_other")
            ctx = [allc[a] for a in reversed(chain) if a in allc and allc[a].timestamp <= b.timestamp]

            def cd(c: Comment, h=None) -> dict:
                d = {"id": c.id, "text": c.text, "timestamp": c.timestamp,
                     "parent_id": c.parent_id, "quotes": c.quotes}
                if h is not None:
                    d["hops"] = h
                return d

            items.append({"item_id": f"{tid}_{b.id}", "thread_id": tid, "B": cd(b),
                          "candidates": {"A1": cd(*pair[0]), "A2": cd(*pair[1])},
                          "context": [cd(c) for c in ctx], "label": "unlabeled", "slices": slices})
            type_count[t] += 1
            made += 1
    return items


# ------------------------------------------------------------------ annotation sheet
def relation(c: dict) -> str:
    h = c.get("hops")
    if h == 1:
        return "B replies DIRECTLY to this comment"
    if h:
        return f"ancestor of B, {h} reply steps up (indirect)"
    return "different branch (no reply path to B)"


SHEET_COLS = ["item_id", "thread_context", "B_quotes", "B_text", "A1_text", "A1_relation",
              "A2_text", "A2_relation", "label", "evidence_span_A", "evidence_span_B", "tags", "note"]


def write_sheet(items: List[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel opens it correctly
        w = csv.DictWriter(f, fieldnames=SHEET_COLS)
        w.writeheader()
        for it in items:
            ctx = " || ".join(c["text"][:300] for c in it["context"][-2:])
            w.writerow({"item_id": it["item_id"], "thread_context": ctx,
                        "B_quotes": " | ".join(it["B"]["quotes"]), "B_text": it["B"]["text"],
                        "A1_text": it["candidates"]["A1"]["text"], "A1_relation": relation(it["candidates"]["A1"]),
                        "A2_text": it["candidates"]["A2"]["text"], "A2_relation": relation(it["candidates"]["A2"]),
                        "label": "", "evidence_span_A": "", "evidence_span_B": "", "tags": "", "note": ""})


# --------------------------------------------------------------------- ConvoKit I/O
def load_cmv(corpus_path: Optional[str] = None) -> Dict[str, List[dict]]:
    try:
        from convokit import Corpus, download
    except ImportError as e:
        raise SystemExit("pip install convokit") from e
    path = corpus_path or download("winning-args-corpus")
    corpus = Corpus(filename=path)
    threads: Dict[str, List[dict]] = defaultdict(list)
    for u in corpus.iter_utterances():
        threads[u.conversation_id].append({
            "id": u.id, "text": u.text, "timestamp": u.timestamp,
            "reply_to": u.reply_to, "speaker": u.speaker.id if u.speaker else ""})
    return threads


def cmd_inspect(args) -> None:
    threads = load_cmv(args.corpus)
    print(f"{len(threads)} threads, {sum(len(v) for v in threads.values())} utterances")
    for tid in list(threads)[: args.n]:
        print(f"\n=== thread {tid} ({len(threads[tid])} utterances)")
        for u in threads[tid][:6]:
            print(f"- id={u['id']} reply_to={u['reply_to']} t={u['timestamp']} speaker={u['speaker']}")
            print("   ", repr((u["text"] or "")[:160]))
    body, quotes = clean("&gt; some quoted claim here\n\n&amp;#8710; my [link text](http://x.com/a) reply &amp; reasoning")
    print("\nquote parser self-check:", repr(body), quotes)


def cmd_build(args) -> None:
    exclude = set()
    for p in args.exclude or []:
        with open(p, encoding="utf-8") as f:
            exclude |= {json.loads(l)["thread_id"] for l in f if l.strip()}
    items = build_items_from_threads(load_cmv(args.corpus), args.n, args.seed,
                                     max_per_thread=args.max_per_thread, exclude_threads=exclude)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "items_unlabeled.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in items)
    for k in (1, 2):
        write_sheet(items, out / f"sheet_annotator{k}.csv")
    print(f"{len(items)} items from {len({i['thread_id'] for i in items})} threads -> {out}/")
    print("types:", dict(Counter(i['slices'][0] for i in items)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inspect")
    i.add_argument("--n", type=int, default=2)
    i.add_argument("--corpus", default=None)
    b = sub.add_parser("build")
    b.add_argument("--n", type=int, required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--seed", type=int, default=13)
    b.add_argument("--max-per-thread", type=int, default=2)
    b.add_argument("--exclude", nargs="*", help="items jsonl whose threads must not be reused (e.g. pilot)")
    b.add_argument("--corpus", default=None, help="path of a saved ConvoKit corpus (default: download/cache)")
    a = ap.parse_args()
    {"inspect": cmd_inspect, "build": cmd_build}[a.cmd](a)
