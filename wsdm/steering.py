"""steering.py -- data model, baselines and the proposed gated Steering score.

Task (one evaluation item): given a reply B and two earlier candidate arguments
A1, A2 in the same thread, decide which of A1/A2 steers B more.

Item JSONL schema (one JSON object per line):
{
  "item_id": "t1_001", "thread_id": "t1",
  "B": {"id": "b1", "text": "...", "timestamp": 1700000100, "parent_id": "a1",
        "quotes": ["quoted span", ...]},
  "candidates": {
     "A1": {"id": "a1", "text": "...", "timestamp": 1700000000, "hops": 1},
     "A2": {"id": "a2", "text": "...", "timestamp": 1700000050, "hops": null}
  },
  "context": [{"id": "...", "text": "...", "timestamp": ...}],   # optional ancestors of B
  "label": "A1>A2" | "A1<A2" | "tie" | "insufficient",
  "slices": ["high_sim_other_branch", "frame_shift", ...]          # optional
}
`hops` = number of reply steps from B up to the candidate (1 = B replies directly
to it, >=2 = indirect ancestor, null = different branch).

Extraction JSONL (features for the proposed score; produced by llm.py `extract` or
by hand; it must NOT contain the annotators' steering label):
{"A_id": "a1", "B_id": "b1",
 "span_pair_ok": true, "specific_reference": false,
 "uptake_level": "named_premise"|"direct_reply_premise"|"indirect_specific"|"none",
 "d_aspect": 0|0.5|1, "d_lens": 0|0.5|1,
 "frame_A": {"aspect": "...", "lens": "..."}, "frame_B": {...},
 "span_A": "...", "span_B": "...", "uptake_type": "...", "development": "..."}
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
LABELS = {"A1>A2", "A1<A2", "tie", "insufficient"}
ORDERED = {"A1>A2", "A1<A2"}
KEYS = ("A1", "A2")


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


# --------------------------------------------------------------------------- data
@dataclass
class Comment:
    id: str
    text: str
    timestamp: float
    parent_id: Optional[str] = None
    quotes: List[str] = field(default_factory=list)
    hops: Optional[int] = None  # candidates only


@dataclass
class Item:
    item_id: str
    thread_id: str
    B: Comment
    candidates: Dict[str, Comment]
    label: str
    slices: List[str] = field(default_factory=list)
    context: List[Comment] = field(default_factory=list)

    def visible_context(self) -> List[Comment]:
        """Only context available at or before B (no look-ahead, per the definition)."""
        return [c for c in self.context if c.timestamp <= self.B.timestamp]


def _comment(d: dict) -> Comment:
    return Comment(
        id=str(d["id"]), text=d["text"], timestamp=float(d["timestamp"]),
        parent_id=d.get("parent_id"), quotes=list(d.get("quotes") or []),
        hops=d.get("hops"),
    )


def load_items(path: str, allow_unlabeled: bool = False) -> List[Item]:
    """allow_unlabeled=True accepts label == "unlabeled" (used before annotation, e.g. for extraction)."""
    items: List[Item] = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            d = json.loads(line)
            if d["label"] not in LABELS and not (allow_unlabeled and d["label"] == "unlabeled"):
                raise ValueError(f"{path}:{ln}: bad label {d['label']!r}")
            if set(d["candidates"]) != set(KEYS):
                raise ValueError(f"{path}:{ln}: candidates must be exactly A1 and A2")
            items.append(Item(
                item_id=str(d["item_id"]), thread_id=str(d["thread_id"]),
                B=_comment(d["B"]),
                candidates={k: _comment(v) for k, v in d["candidates"].items()},
                label=d["label"], slices=list(d.get("slices") or []),
                context=[_comment(c) for c in d.get("context") or []],
            ))
    return items


def compute_hops(parent_of: Dict[str, Optional[str]], a_id: str, b_id: str) -> Optional[int]:
    """Reply steps from B up to A (1 = direct reply). None if A is not an ancestor of B."""
    cur, steps = b_id, 0
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        cur = parent_of.get(cur)
        steps += 1
        if cur == a_id:
            return steps
    return None


def quote_match(a: Comment, b: Comment, thresh: float = 0.6) -> bool:
    """True if one of B's quoted spans is (mostly) contained in A's text."""
    a_tok = set(tokenize(a.text))
    for q in b.quotes:
        q_tok = set(tokenize(q))
        if len(q_tok) >= 3 and len(q_tok & a_tok) / len(q_tok) >= thresh:
            return True
    return False


def pair_key(a_id: str, b_id: str) -> str:
    return f"{a_id}|{b_id}"


# ----------------------------------------------------------------------- embedders
class TfidfEmbedder:
    """Dependency-free TF-IDF cosine. Fitted without labels, so fitting on the
    texts of the eval set is unsupervised; prefer fitting on train threads."""

    def fit(self, texts: Iterable[str]) -> "TfidfEmbedder":
        df: Counter = Counter()
        n = 0
        for t in texts:
            df.update(set(tokenize(t)))
            n += 1
        self.idf = {w: math.log((1 + n) / (1 + c)) + 1.0 for w, c in df.items()}
        self.default_idf = math.log(1 + n) + 1.0
        return self

    def _vec(self, text: str) -> Dict[str, float]:
        tf = Counter(tokenize(text))
        v = {w: c * self.idf.get(w, self.default_idf) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def sim(self, a: str, b: str) -> float:
        va, vb = self._vec(a), self._vec(b)
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(w, 0.0) for w, x in va.items())


class SentenceTransformerEmbedder:
    """Optional: pip install sentence-transformers. Use a multilingual model for Vietnamese."""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import
        self.model = SentenceTransformer(model_name)
        self._cache: Dict[str, "object"] = {}

    def fit(self, texts: Iterable[str]) -> "SentenceTransformerEmbedder":
        return self

    def _emb(self, text: str):
        if text not in self._cache:
            self._cache[text] = self.model.encode(text, normalize_embeddings=True)
        return self._cache[text]

    def sim(self, a: str, b: str) -> float:
        return float((self._emb(a) * self._emb(b)).sum())


# ------------------------------------------------------------------------ scorers
class Scorer:
    name = "base"

    def fit(self, items: List[Item]) -> None:
        pass

    def score(self, item: Item, key: str) -> float:
        raise NotImplementedError

    def explain(self, item: Item, key: str) -> dict:
        return {}


class RandomScorer(Scorer):
    """Sanity floor: deterministic pseudo-random score per (item, candidate)."""
    name = "random"

    def score(self, item: Item, key: str) -> float:
        h = hashlib.md5(f"{item.item_id}|{key}".encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF


class CosineScorer(Scorer):
    """B1: embedding cosine similarity between A and B."""
    name = "cosine"

    def __init__(self, embedder=None):
        self.emb = embedder or TfidfEmbedder()

    def fit(self, items: List[Item]) -> None:
        texts = []
        for it in items:
            texts.append(it.B.text)
            texts.extend(c.text for c in it.candidates.values())
        self.emb.fit(texts)

    def score(self, item: Item, key: str) -> float:
        return self.emb.sim(item.candidates[key].text, item.B.text)


class ReplyQuoteScorer(Scorer):
    """B2: structural evidence x similarity.
    factor = 1.0 for a direct reply or a matched quote, 0.5 for an indirect ancestor
    (>=2 hops), 0 for another branch. Both candidates at 0 => tie (no hidden tie-break)."""
    name = "reply_quote"

    def __init__(self, embedder=None):
        self.cos = CosineScorer(embedder)

    def fit(self, items: List[Item]) -> None:
        self.cos.fit(items)

    @staticmethod
    def factor(item: Item, key: str) -> float:
        a = item.candidates[key]
        if a.hops == 1 or quote_match(a, item.B):
            return 1.0
        if a.hops is not None and a.hops >= 2:
            return 0.5
        return 0.0

    def score(self, item: Item, key: str) -> float:
        return self.factor(item, key) * self.cos.score(item, key)

    def explain(self, item: Item, key: str) -> dict:
        return {"structure_factor": self.factor(item, key)}


# --------------------------------------------------------------- proposed (gated)
# Rubric from the definition doc: heuristic, NOT a proven weighting -> run the sensitivity ablation.
LEVELS = {"named_premise": 1.0, "direct_reply_premise": 0.8, "indirect_specific": 0.6, "none": 0.0}
D_VALUES = (0.0, 0.5, 1.0)


def load_extractions(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out[pair_key(str(d["A_id"]), str(d["B_id"]))] = d
    return out


class ProposedScorer(Scorer):
    """S(A->B|C) = 1[t_A < t_B] * G * U * D   (variant 'full').

    G : evidence gate = (trace signal) AND (verified A-B span pair).
        trace = direct reply (hops==1) OR matched quote OR extraction.specific_reference.
        A reply/quote alone never passes: span_pair_ok must also be true.
    U : G * rubric(uptake_level);  U_raw is the same rubric without the gate.
    D : min(d_aspect, d_lens);     D_mean is the mean (ablation).

    Variants (ablation; the doc leaves 'U only' / 'D only' open, definitions used here):
      full     time * G * U * D
      u_only   time * G * U              (no frame retention)
      d_only   time * G * D              (no uptake strength)
      ungated  time * U_raw * D          (gate removed)
      dmean    time * G * U * mean(d_aspect, d_lens)
    """
    VARIANTS = ("full", "u_only", "d_only", "ungated", "dmean")

    def __init__(self, extractions: Dict[str, dict], variant: str = "full"):
        if variant not in self.VARIANTS:
            raise ValueError(f"variant must be one of {self.VARIANTS}")
        self.ex = extractions
        self.variant = variant
        self.name = "proposed" if variant == "full" else f"proposed_{variant}"

    def components(self, item: Item, key: str) -> dict:
        a, b = item.candidates[key], item.B
        ex = self.ex.get(pair_key(a.id, b.id))
        c = {"time_ok": a.timestamp < b.timestamp, "has_extraction": ex is not None,
             "trace": [], "span_pair_ok": False, "G": 0, "U_raw": 0.0, "U": 0.0,
             "d_aspect": 0.0, "d_lens": 0.0, "D": 0.0, "D_mean": 0.0}
        if ex is None:
            return c
        if a.hops == 1:
            c["trace"].append("direct_reply")
        if quote_match(a, b):
            c["trace"].append("quote")
        if ex.get("specific_reference"):
            c["trace"].append("specific_reference")
        c["span_pair_ok"] = bool(ex.get("span_pair_ok"))
        c["G"] = int(bool(c["trace"]) and c["span_pair_ok"])
        c["U_raw"] = LEVELS.get(ex.get("uptake_level", "none"), 0.0)
        c["U"] = c["G"] * c["U_raw"]
        da, dl = float(ex.get("d_aspect", 0)), float(ex.get("d_lens", 0))
        if da not in D_VALUES or dl not in D_VALUES:
            raise ValueError(f"d_aspect/d_lens must be in {D_VALUES} for pair {a.id}|{b.id}")
        c["d_aspect"], c["d_lens"] = da, dl
        c["D"], c["D_mean"] = min(da, dl), (da + dl) / 2
        return c

    def score(self, item: Item, key: str) -> float:
        c = self.components(item, key)
        t = 1.0 if c["time_ok"] else 0.0
        v = self.variant
        if v == "full":
            return t * c["G"] * c["U"] * c["D"]
        if v == "u_only":
            return t * c["G"] * c["U"]
        if v == "d_only":
            return t * c["G"] * c["D"]
        if v == "ungated":
            return t * c["U_raw"] * c["D"]
        return t * c["G"] * c["U"] * c["D_mean"]  # dmean

    def explain(self, item: Item, key: str) -> dict:
        """Explanation record (frame A/B, spans, uptake type, retention) + reason when S=0."""
        a, b = item.candidates[key], item.B
        ex = self.ex.get(pair_key(a.id, b.id)) or {}
        c = self.components(item, key)
        s = self.score(item, key)
        reason = None
        if s == 0:
            if not c["has_extraction"]:
                reason = "no extraction for this pair"
            elif not c["time_ok"]:
                reason = "t_A >= t_B"
            elif not c["trace"]:
                reason = "no trace signal (no direct reply / quote / specific reference)"
            elif not c["span_pair_ok"]:
                reason = "A-B span pair not verified (reply/quote alone is not enough)"
            elif c["U_raw"] == 0:
                reason = "uptake level 'none'"
            else:
                reason = "frame not retained (D=0)"
            reason += "; S=0 means insufficient evidence detected, not proof of no influence"
        return {"S": s, "reason": reason, "components": c,
                "frame_A": ex.get("frame_A"), "frame_B": ex.get("frame_B"),
                "span_A": ex.get("span_A"), "span_B": ex.get("span_B"),
                "uptake_type": ex.get("uptake_type"), "development": ex.get("development")}
