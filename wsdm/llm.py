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
 "development": "new_reason" | "consequence" | "proposal" | "none"}

EVIDENCE RULES:
- span_A and span_B must be exact, case-sensitive, contiguous substrings copied from A and B. Preserve every character,
  including Markdown punctuation. Never paraphrase, repair, or normalize a span.
- Select the shortest clause or sentence that is sufficient to demonstrate the A-B link. Do not copy a whole argument
  when a shorter exact span works. Each span must be at most 320 characters.
- span_pair_ok=true only when both non-empty spans form an observable pair: span_B actually uses, challenges, applies,
  or develops the content in span_A. Topic overlap or reply structure alone is not enough.
- If span_pair_ok=false, set uptake_level="none" and uptake_type="none". If uptake_level="none", set
  span_pair_ok=false. Do not claim uptake while rejecting its evidence pair.
- indirect_specific means there is no direct-reply/quote trace but B makes a content-specific reference to A; therefore
  it requires span_pair_ok=true, specific_reference=true, and uptake_type="indirect".
- direct_reply_premise requires span_pair_ok=true and uptake_type="direct_reply". A direct reply alone is insufficient.
- named_premise requires span_pair_ok=true and uptake_type other than "none"; use uptake_type="quote" for a quotation.

FRAME RULES:
- A frame is (aspect, lens). The lens is the actual criterion used to evaluate the aspect, not merely the broad topic.
- d_lens=1 only for clearly the same evaluative criterion; 0.5 only when that same criterion is compatibly narrowed,
  widened, or qualified; 0 when B switches criteria (for example, individual rights to aggregate welfare), even when
  B discusses the same aspect or quotes A. Apply the analogous rule to d_aspect.
- Disagreement does not itself imply a frame shift, and quotation does not itself imply frame retention."""

MAX_EVIDENCE_SPAN_CHARS = 320

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
        elif len(d[name]) > MAX_EVIDENCE_SPAN_CHARS:
            errors.append(f"{name} exceeds {MAX_EVIDENCE_SPAN_CHARS} characters; select a concise verbatim span")
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
    span_pair_ok = d.get("span_pair_ok")
    specific_reference = d.get("specific_reference")
    uptake_level = d.get("uptake_level")
    uptake_type = d.get("uptake_type")
    if span_pair_ok is False and uptake_level not in {None, "none"}:
        errors.append("span_pair_ok=false requires uptake_level='none'")
    if uptake_level == "none" and span_pair_ok is not False:
        errors.append("uptake_level='none' requires span_pair_ok=false")
    if uptake_level == "none" and uptake_type not in {None, "none"}:
        errors.append("uptake_level='none' requires uptake_type='none'")
    if uptake_type == "none" and uptake_level not in {None, "none"}:
        errors.append("uptake_type='none' requires uptake_level='none'")
    if uptake_level == "indirect_specific":
        if span_pair_ok is not True:
            errors.append("uptake_level='indirect_specific' requires span_pair_ok=true")
        if specific_reference is not True:
            errors.append("uptake_level='indirect_specific' requires specific_reference=true")
        if uptake_type != "indirect":
            errors.append("uptake_level='indirect_specific' requires uptake_type='indirect'")
    if uptake_type == "indirect" and specific_reference is not True:
        errors.append("uptake_type='indirect' requires specific_reference=true")
    if uptake_level == "direct_reply_premise":
        if span_pair_ok is not True:
            errors.append("uptake_level='direct_reply_premise' requires span_pair_ok=true")
        if uptake_type != "direct_reply":
            errors.append("uptake_level='direct_reply_premise' requires uptake_type='direct_reply'")
    if uptake_type == "direct_reply" and item.candidates[key].hops != 1:
        errors.append("uptake_type='direct_reply' requires a direct-reply structural relation")
    if uptake_level == "named_premise" and (span_pair_ok is not True or uptake_type == "none"):
        errors.append("uptake_level='named_premise' requires span_pair_ok=true and a non-none uptake_type")
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
        indirect_specific = ok and not direct
        return json.dumps({
            "frame_A": {"aspect": "mock", "lens": "mock"}, "frame_B": {"aspect": "mock", "lens": "mock"},
            "span_A": a[:40], "span_B": b[:40], "span_pair_ok": ok,
            "specific_reference": indirect_specific,
            "uptake_level": ("direct_reply_premise" if direct else "indirect_specific") if ok else "none",
            "uptake_type": ("direct_reply" if direct else "indirect") if ok else "none",
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


_RETRY_DEPENDENCIES = {
    "span_A": {"span_pair_ok", "uptake_level", "uptake_type"},
    "span_B": {"span_pair_ok", "uptake_level", "uptake_type"},
    "span_pair_ok": {"span_A", "span_B", "uptake_level", "uptake_type"},
    "specific_reference": {"uptake_level", "uptake_type"},
    "uptake_level": {"span_pair_ok", "specific_reference", "uptake_type"},
    "uptake_type": {"span_pair_ok", "specific_reference", "uptake_level"},
}


def _retry_field_context(errors: list[str]) -> dict:
    """Identify rejected fields and fields that must be rechecked with them."""
    invalid = {
        name for name in EXTRACTION_KEYS
        if any(name in error for error in errors)
    }
    if any(error == "unparseable JSON" for error in errors):
        invalid.add("entire_json")
    if any(error.startswith(("missing keys:", "unexpected keys:")) for error in errors):
        invalid.add("schema")
    dependencies = set()
    for name in invalid:
        dependencies.update(_RETRY_DEPENDENCIES.get(name, set()))
    dependencies.difference_update(invalid)
    return {
        "invalid_fields": sorted(invalid),
        "dependent_fields_to_recheck": sorted(dependencies),
    }


def _visible_whitespace(text: str) -> str:
    """Diagnostic rendering only; these visible markers must never become evidence."""
    return text.replace(" ", "␠").replace("\t", "⇥").replace("\n", "⏎\n")


def _correction_task(item: Item, key: str, previous_raw: str, errors: list[str]) -> str:
    """Build a retry-only repair request without changing the initial extraction task."""
    context = _retry_field_context(errors)
    a_text = item.candidates[key].text[:3000]
    b_text = item.B.text[:3000]
    return "\n".join([
        EXTRACT_TASK,
        "",
        "CORRECTION RETRY (one retry maximum). Repair the previous JSON; do not redo the task from scratch.",
        "Preserve fields that were valid. Repair the invalid fields and any dependent fields listed below, then",
        "revalidate the entire complete JSON object before returning it. Return JSON only.",
        "",
        "PREVIOUS INVALID RESPONSE (preserved verbatim):",
        "<PREVIOUS_INVALID_RESPONSE>",
        previous_raw,
        "</PREVIOUS_INVALID_RESPONSE>",
        "",
        "STRUCTURED VALIDATION ERRORS:",
        json.dumps(errors, ensure_ascii=False, indent=2),
        "INVALID FIELDS:",
        json.dumps(context["invalid_fields"], ensure_ascii=False),
        "DEPENDENT FIELDS TO RECHECK:",
        json.dumps(context["dependent_fields_to_recheck"], ensure_ascii=False),
        "Preserve fields not listed above. Repair only invalid fields and dependencies needed for consistency,",
        "then revalidate every field and return one complete JSON object with exactly the required keys.",
        "",
        "VALID UPTAKE COMBINATIONS:",
        "| uptake_level | span_pair_ok | specific_reference | uptake_type |",
        "| none | false | true or false | none |",
        "| indirect_specific | true | true | indirect |",
        "| direct_reply_premise | true | true or false | direct_reply |",
        "| named_premise | true | true or false | quote or direct_reply |",
        "| named_premise | true | true | indirect |",
        "A non-none uptake level is never valid with span_pair_ok=false.",
        "uptake_type=direct_reply additionally requires that B structurally replies directly to A.",
        "",
        "SOURCE BOUNDARIES AND EXACT-SPAN RULES:",
        "- span_A may be copied only from SOURCE A. span_B may be copied only from SOURCE B.",
        "- Never copy a span from the other source.",
        "- Spans remain exact, case-sensitive, contiguous, at most 320 characters, with Markdown and whitespace preserved.",
        "- Do not fuzzy-match, paraphrase, normalize, repair punctuation, or silently alter whitespace.",
        "- The JSON-string renderings below are authoritative for copying. The visible renderings are diagnostic only:",
        "  ␠ marks a space, ⇥ marks a tab, and ⏎ marks a newline. Do not copy those marker characters.",
        "",
        "SOURCE A (authoritative JSON string):",
        json.dumps(a_text, ensure_ascii=False),
        "SOURCE A (whitespace-visible diagnostic):",
        _visible_whitespace(a_text),
        "",
        "SOURCE B (authoritative JSON string):",
        json.dumps(b_text, ensure_ascii=False),
        "SOURCE B (whitespace-visible diagnostic):",
        _visible_whitespace(b_text),
    ])


def _extract_response(client: LLMClient, item: Item, key: str,
                      correction: Optional[list[str]] = None,
                      previous_raw: Optional[str] = None):
    task = EXTRACT_TASK
    if correction:
        if previous_raw is None:
            raise ValueError("correction retry requires the previous raw response")
        task = _correction_task(item, key, previous_raw, correction)
    prompt = "\n\n".join([DEFINITION, task, render_pair(item, key)])
    raw = client.complete(prompt)
    return raw, parse_json(raw)


def _finalize_extraction(d: dict, item: Item, key: str) -> dict:
    validation_errors = validate_extraction(d, item, key)
    a = item.candidates[key]
    d["A_id"], d["B_id"] = a.id, item.B.id
    d["validation"] = {"valid": not validation_errors, "errors": validation_errors,
                       "verbatim_spans_checked": True,
                       "cross_field_consistency_checked": True}
    return d


def extract_pair(client: LLMClient, item: Item, key: str) -> Optional[dict]:
    """Single extraction attempt retained for callers that explicitly do not want retry."""
    _, d = _extract_response(client, item, key)
    if d is None:
        return None
    return _finalize_extraction(d, item, key)


def extract_pair_with_retry(client: LLMClient, item: Item, key: str, max_retries: int = 1):
    """Extract with bounded correction retries and return (extraction, auditable attempts).

    No invalid output is normalized or converted to a score. Each raw response and its
    parse/validation failure is retained for the caller to persist.
    """
    if max_retries not in {0, 1}:
        raise ValueError("max_retries must be 0 or 1")
    attempts = []
    correction = None
    previous_raw = None
    final = None
    for attempt_index in range(max_retries + 1):
        repair_context = _retry_field_context(correction) if correction else None
        raw, parsed = _extract_response(
            client, item, key, correction=correction, previous_raw=previous_raw,
        )
        if parsed is None:
            errors = ["unparseable JSON"]
            final = None
        else:
            final = _finalize_extraction(parsed, item, key)
            errors = list(final["validation"]["errors"])
        attempt_record = {
            "attempt": attempt_index + 1,
            "kind": "initial" if attempt_index == 0 else "correction_retry",
            "raw_response": raw,
            "parsed_json": parsed is not None,
            "valid": parsed is not None and not errors,
            "errors": errors,
        }
        if repair_context is not None:
            attempt_record["repair_context"] = repair_context
        attempts.append(attempt_record)
        if parsed is not None and not errors:
            return final, attempts
        correction = errors
        previous_raw = raw
    return final, attempts


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
