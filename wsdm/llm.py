"""llm.py -- LLM-backed parts: B3 direct scoring and structured frame/uptake extraction.

Usage (extraction for the proposed score):
    python llm.py extract --items data/test.jsonl --out data/extractions_test.jsonl \
        --model claude-sonnet-5-5 --cache cache/llm.jsonl
Use --model mock to dry-run the whole pipeline offline (heuristic stand-in, NOT a result).

Design rules taken from the definition doc:
  * the LLM sees only context at or before B (Item.visible_context),
  * extraction prompts never ask for a steering label and never see annotator labels,
  * B3 gets exactly the same context/evidence as the proposed method.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

from steering import Item, Scorer, load_items, pair_key

SYSTEM = "You are a careful annotator of online argumentation. Reply with a single JSON object only."

DEFINITION = """DEFINITION. Argument A steers reply B when: (i) A precedes B; (ii) B shows observable evidence of
taking up a premise, framing or specific content from A; (iii) B uses that content to continue arguing in the same
evaluative direction as A. B may agree or disagree with A's conclusion. Frame F = (aspect, lens): aspect = the concrete
issue being discussed; lens = the criterion/basis used to evaluate it. "Same direction" = B keeps a compatible aspect AND lens.
Not enough on their own: same topic, a plain reply, a quote whose content is not used, bare agreement without reasoning.
Steering is evidence in observed discourse, NOT established causal influence."""

SCORE_RUBRIC = """RUBRIC for the final score in [0,1]:
gate G=1 only if there is (a) a trace (reply/quote/reference or content-specific reference) AND (b) a verified A-B span pair
showing B really uses A's content; otherwise score = 0.
U (uptake strength after gate): 1.0 = quotes/names A and uses a specific premise; 0.8 = direct reply using a premise whose
span can be aligned; 0.6 = indirect reference with content-specific signs and a clear link.
D (direction retention): d_aspect, d_lens in {0, 0.5, 1} (0 = different/changed criterion; 0.5 = compatible but widened/narrowed;
1 = clearly the same); D = min(d_aspect, d_lens).
score = G * U * D. Example: U=0.8, d_aspect=1, d_lens=0.5 -> 0.4."""

SCORE_TASK = """TASK: SCORE. Give the steering score of A -> B following the rubric. Use only the information below.
Return JSON: {"score": <float 0..1>, "rationale": "<one or two sentences>"}"""

EXTRACT_TASK = """TASK: EXTRACT. Do NOT decide whether A steers B. Extract the fields below from the texts.
Return JSON with exactly these keys:
{"frame_A": {"aspect": str, "lens": str}, "frame_B": {"aspect": str, "lens": str},
 "span_A": str (verbatim span of A that B takes up, "" if none), "span_B": str (verbatim span of B that uses it, "" if none),
 "span_pair_ok": bool (B really uses/responds to the content of span_A),
 "specific_reference": bool (B refers to content specific to A even without reply/quote),
 "uptake_level": "named_premise" | "direct_reply_premise" | "indirect_specific" | "none",
 "uptake_type": "quote" | "direct_reply" | "indirect" | "none",
 "d_aspect": 0 | 0.5 | 1, "d_lens": 0 | 0.5 | 1,
 "development": "new_reason" | "consequence" | "proposal" | "none"}"""

EXTRACTION_KEYS = {
    "frame_A", "frame_B", "span_A", "span_B", "span_pair_ok", "specific_reference",
    "uptake_level", "uptake_type", "d_aspect", "d_lens", "development",
}
EXTRACTION_ENUMS = {
    "uptake_level": {"named_premise", "direct_reply_premise", "indirect_specific", "none"},
    "uptake_type": {"quote", "direct_reply", "indirect", "none"},
    "development": {"new_reason", "consequence", "proposal", "none"},
}


def validate_extraction(d: dict, item: Item, key: str) -> list[str]:
    """Validate schema and require claimed evidence spans to be verbatim source text."""
    errors = []
    missing = sorted(EXTRACTION_KEYS - set(d))
    extra = sorted(set(d) - EXTRACTION_KEYS)
    if missing:
        errors.append(f"missing keys: {missing}")
    if extra:
        errors.append(f"unexpected keys: {extra}")
    for frame_key in ("frame_A", "frame_B"):
        frame = d.get(frame_key)
        if not isinstance(frame, dict) or set(frame) != {"aspect", "lens"}:
            errors.append(f"{frame_key} must contain exactly aspect and lens")
        elif not all(isinstance(frame.get(name), str) for name in ("aspect", "lens")):
            errors.append(f"{frame_key} values must be strings")
    for name in ("span_A", "span_B"):
        if not isinstance(d.get(name), str):
            errors.append(f"{name} must be a string")
    for name in ("span_pair_ok", "specific_reference"):
        if type(d.get(name)) is not bool:
            errors.append(f"{name} must be boolean")
    for name, allowed in EXTRACTION_ENUMS.items():
        if d.get(name) not in allowed:
            errors.append(f"{name} must be one of {sorted(allowed)}")
    for name in ("d_aspect", "d_lens"):
        try:
            value = float(d.get(name))
        except (TypeError, ValueError):
            errors.append(f"{name} must be numeric")
        else:
            if value not in {0.0, 0.5, 1.0}:
                errors.append(f"{name} must be 0, 0.5, or 1")
    a_text, b_text = item.candidates[key].text, item.B.text
    span_a, span_b = d.get("span_A"), d.get("span_B")
    if isinstance(span_a, str) and span_a and span_a not in a_text:
        errors.append("span_A is not a verbatim substring of A")
    if isinstance(span_b, str) and span_b and span_b not in b_text:
        errors.append("span_B is not a verbatim substring of B")
    if d.get("span_pair_ok") and (not span_a or not span_b):
        errors.append("span_pair_ok=true requires non-empty span_A and span_B")
    return errors


def render_pair(item: Item, key: str, max_chars: int = 3000, ctx_n: int = 3) -> str:
    a, b = item.candidates[key], item.B
    if a.hops == 1:
        rel = "B replies directly to A."
    elif a.hops:
        rel = f"A is an ancestor of B, {a.hops} reply steps up (indirect)."
    else:
        rel = "A is in a different branch of the thread (no reply path to B)."
    ctx = "\n".join(f"- {c.text[:600]}" for c in item.visible_context()[-ctx_n:]) or "(none)"
    quotes = "\n".join(f"- {q}" for q in b.quotes) or "(none)"
    return (f"Thread context before B:\n{ctx}\n\nStructure: {rel}\n"
            f"B quotes:\n{quotes}\n\n<A>\n{a.text[:max_chars]}\n</A>\n\n<B>\n{b.text[:max_chars]}\n</B>")


def parse_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------- clients
class LLMClient:
    model = "base"

    def complete(self, prompt: str, system: str = SYSTEM) -> str:
        raise NotImplementedError


class AnthropicClient(LLMClient):
    """Needs `pip install anthropic` and ANTHROPIC_API_KEY. Set --model to the model you can use."""

    def __init__(self, model: str, max_tokens: int = 700):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise SystemExit("pip install anthropic (and set ANTHROPIC_API_KEY) to use real LLM calls") from e
        self._c = anthropic.Anthropic()
        self.model, self.max_tokens, self._use_temp = model, max_tokens, True

    def complete(self, prompt: str, system: str = SYSTEM) -> str:
        kw = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                  messages=[{"role": "user", "content": prompt}])
        try:
            resp = self._c.messages.create(**kw, **({"temperature": 0} if self._use_temp else {}))
        except Exception:
            if not self._use_temp:
                raise
            self._use_temp = False  # some models reject `temperature`; retry once without it
            resp = self._c.messages.create(**kw)
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class OllamaClient(LLMClient):
    """Local model via Ollama's HTTP API (no extra dependency). Use --model ollama:<name>,
    e.g. ollama:qwen2.5:14b. Host from OLLAMA_HOST (default http://localhost:11434).
    num_ctx is raised because Ollama's small default context silently truncates long prompts."""

    def __init__(self, model: str, num_ctx: int = 8192, timeout: int = 600):
        self.model, self.num_ctx, self.timeout = model, num_ctx, timeout
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.host = (host if host.startswith("http") else f"http://{host}").rstrip("/")
        self.url = self.host + "/api/chat"

    def check_available(self) -> None:
        import urllib.request
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as response:
                payload = json.loads(response.read())
        except (OSError, ValueError) as exc:
            raise SystemExit(
                f"Cannot reach Ollama at {self.host} ({exc}). Start it with `ollama serve`."
            ) from exc
        names = {entry.get("name") for entry in payload.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            available = ", ".join(sorted(name for name in names if name)) or "none"
            raise SystemExit(
                f"Ollama model {self.model!r} is not installed. Available: {available}. "
                f"Run `ollama pull {self.model}` first."
            )

    def complete(self, prompt: str, system: str = SYSTEM) -> str:
        import urllib.request
        body = json.dumps({
            "model": self.model, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "seed": 0},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())["message"]["content"]
        except OSError as e:
            raise SystemExit(f"Cannot reach Ollama at {self.url} ({e}). Is `ollama serve` running "
                             f"and the model pulled (`ollama pull {self.model}`)?") from e


class MockClient(LLMClient):
    """Offline stand-in for smoke tests only: token-overlap heuristics. Never report its numbers."""
    model = "mock"

    @staticmethod
    def _ab(prompt: str):
        a = re.search(r"<A>\n(.*?)\n</A>", prompt, re.S).group(1)
        b = re.search(r"<B>\n(.*?)\n</B>", prompt, re.S).group(1)
        ta, tb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
        return a, b, len(ta & tb) / max(1, len(ta | tb)), "replies directly" in prompt

    def complete(self, prompt: str, system: str = SYSTEM) -> str:
        a, b, jac, direct = self._ab(prompt)
        if "TASK: SCORE" in prompt:
            return json.dumps({"score": round(min(1.0, 2 * jac) * (1.0 if direct else 0.3), 2),
                               "rationale": "mock"})
        ok = jac > 0.15
        return json.dumps({
            "frame_A": {"aspect": "mock", "lens": "mock"}, "frame_B": {"aspect": "mock", "lens": "mock"},
            "span_A": a[:40], "span_B": b[:40], "span_pair_ok": ok, "specific_reference": False,
            "uptake_level": ("direct_reply_premise" if direct else "indirect_specific") if ok else "none",
            "uptake_type": "direct_reply" if direct else "indirect",
            "d_aspect": 1 if ok else 0, "d_lens": 0.5 if ok else 0, "development": "none"})


class CachedClient(LLMClient):
    """Disk cache keyed by (model, system, prompt): reruns are free and reproducible."""

    def __init__(self, inner: LLMClient, path: Optional[str]):
        self.inner, self.path, self.model = inner, path, inner.model
        self.mem: Dict[str, str] = {}
        if path and Path(path).exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        self.mem[d["k"]] = d["v"]

    def complete(self, prompt: str, system: str = SYSTEM) -> str:
        k = hashlib.sha256(f"{self.model}\x00{system}\x00{prompt}".encode()).hexdigest()
        if k not in self.mem:
            self.mem[k] = self.inner.complete(prompt, system)
            if self.path:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"k": k, "v": self.mem[k]}, ensure_ascii=False) + "\n")
        return self.mem[k]


def make_client(model: str, cache: Optional[str]) -> LLMClient:
    if model == "mock":
        inner: LLMClient = MockClient()
    elif model.startswith("ollama:"):
        inner = OllamaClient(model[len("ollama:"):])
        inner.check_available()
    else:
        inner = AnthropicClient(model)
    return CachedClient(inner, cache)


# ---------------------------------------------------------------- B3 + extraction
class LLMDirectScorer(Scorer):
    """B3: LLM scores A->B directly with the same rubric, context and evidence."""
    name = "llm"

    def __init__(self, client: LLMClient):
        self.client = client
        self._notes: Dict[str, dict] = {}

    def score(self, item: Item, key: str) -> float:
        prompt = "\n\n".join([DEFINITION, SCORE_RUBRIC, SCORE_TASK, render_pair(item, key)])
        d = parse_json(self.client.complete(prompt))
        note = {"parse_ok": d is not None}
        s = 0.0
        if d is not None:
            try:
                s = min(1.0, max(0.0, float(d.get("score", 0.0))))
                note["rationale"] = d.get("rationale")
            except (TypeError, ValueError):
                note["parse_ok"] = False
        self._notes[f"{item.item_id}|{key}"] = note
        return s

    def explain(self, item: Item, key: str) -> dict:
        return self._notes.get(f"{item.item_id}|{key}", {})


def extract_pair(client: LLMClient, item: Item, key: str) -> Optional[dict]:
    prompt = "\n\n".join([DEFINITION, EXTRACT_TASK, render_pair(item, key)])
    d = parse_json(client.complete(prompt))
    if d is None:
        return None
    validation_errors = validate_extraction(d, item, key)
    a = item.candidates[key]
    d["A_id"], d["B_id"] = a.id, item.B.id
    d["validation"] = {"valid": not validation_errors, "errors": validation_errors,
                       "verbatim_spans_checked": True}
    return d


def run_extraction(items, client: LLMClient, out_path: str, errors_path: Optional[str] = None) -> int:
    seen, n, failed = set(), 0, 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    error_records = []
    with open(out_path, "w", encoding="utf-8") as f:
        for it in items:
            for key in ("A1", "A2"):
                pk = pair_key(it.candidates[key].id, it.B.id)
                if pk in seen:
                    continue
                seen.add(pk)
                d = extract_pair(client, it, key)
                if d is None:
                    failed += 1
                    error_records.append({"A_id": it.candidates[key].id, "B_id": it.B.id,
                                          "errors": ["unparseable JSON"]})
                    continue
                if not d["validation"]["valid"]:
                    failed += 1
                    error_records.append({"A_id": d["A_id"], "B_id": d["B_id"],
                                          "errors": d["validation"]["errors"]})
                    continue
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                n += 1
    if errors_path:
        error_file = Path(errors_path)
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with error_file.open("w", encoding="utf-8") as handle:
            for record in error_records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"extracted {n} pairs, {failed} unparseable -> {out_path}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--items", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--model", required=True, help="Anthropic model id, or 'mock' for offline dry run")
    e.add_argument("--cache", default=None)
    e.add_argument("--limit", type=int, default=None, help="maximum number of ranking items")
    e.add_argument("--errors", default=None, help="JSONL validation/parse error log")
    args = ap.parse_args()
    items = load_items(args.items, allow_unlabeled=True)
    if args.limit is not None:
        items = items[:args.limit]
    run_extraction(items, make_client(args.model, args.cache), args.out, args.errors)
