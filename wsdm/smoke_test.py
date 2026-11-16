"""smoke_test.py -- end-to-end offline check of split / baselines / proposed score / evaluation.

Toy data mirrors the doc's examples (P1-P3, N1-N5). It only proves the code runs and that the
score behaves as defined; the numbers mean nothing scientifically.
    python smoke_test.py
"""
import json
import subprocess
import sys
from pathlib import Path

from steering import load_items

HERE = Path(__file__).resolve().parent
OUT = HERE / "toy"
TOPICS = ["thi lại", "đồng phục", "bài tập về nhà", "học thêm"]


def mk(i, text, ts, parent=None, quotes=None, hops=None):
    d = {"id": i, "text": text, "timestamp": ts, "parent_id": parent, "quotes": quotes or []}
    if hops is not None:
        d["hops"] = hops
    return d


def ex(a, b, ok, uptake, da, dl, spec=False):
    return {"A_id": a, "B_id": b, "span_pair_ok": ok, "specific_reference": spec,
            "uptake_level": uptake, "d_aspect": da, "d_lens": dl, "uptake_type": "mock",
            "frame_A": {"aspect": "x", "lens": "y"}, "frame_B": {"aspect": "x", "lens": "y"},
            "span_A": "", "span_B": "", "development": "none"}


def build():
    items, exts = [], []
    for k, tp in enumerate(TOPICS):
        press = f"{tp} gây áp lực tâm lý cho học sinh."
        similar = f"{tp} gây căng thẳng cho học sinh."
        cost = f"{tp} làm tăng chi phí tổ chức cho nhà trường."
        ctx = [mk("root", f"Bài đăng gốc về {tp}", 10),
               mk("leak", "phản hồi đến sau B (không được dùng)", 999)]

        def add(tag, A1, A2, B, label, slices):
            iid = f"{tag}_{k}"
            items.append({"item_id": iid, "thread_id": iid, "B": B,
                          "candidates": {"A1": A1, "A2": A2}, "context": ctx,
                          "label": label, "slices": slices})

        # T1 (P1): quote + develop; A2 = high-similarity other branch (N2)
        a1, a2 = mk(f"a1_{k}", press, 100, hops=1), mk(f"a2_{k}", similar, 110)
        b = mk(f"b1_{k}", "Áp lực kéo dài làm giảm khả năng tập trung và kết quả thi.", 200,
               parent=a1["id"], quotes=[press])
        add("T1", a1, a2, b, "A1>A2", ["high_sim_other_branch"])
        exts += [ex(a1["id"], b["id"], True, "named_premise", 1, 1), ex(a2["id"], b["id"], False, "none", 0, 0)]

        # T2 (N4): reply but different aspect; A2 other branch, no trace -> both fail gate
        a1, a2 = mk(f"a1b_{k}", press, 100, hops=1), mk(f"a2b_{k}", cost, 110)
        b = mk(f"b2_{k}", f"Chi phí tổ chức {tp} quá cao.", 200, parent=a1["id"])
        add("T2", a1, a2, b, "insufficient", ["reply_diff_lens"])
        exts += [ex(a1["id"], b["id"], False, "none", 0, 0), ex(a2["id"], b["id"], False, "none", 0, 0)]

        # T3: A1 direct reply but frame changed; A2 = 2-hop ancestor B really builds on (N5 / specific reference)
        a2, a1 = mk(f"a2c_{k}", press, 50), mk(f"a1c_{k}", cost, 100, parent=f"a2c_{k}", hops=1)
        a2["hops"] = 2
        b = mk(f"b3_{k}", f"Áp lực tâm lý khi {tp} làm học sinh mất tập trung, nhất là vào mùa thi.", 200, parent=a1["id"])
        add("T3", a1, a2, b, "A1<A2", ["ancestor_2_hops", "reply_diff_lens"])
        exts += [ex(a1["id"], b["id"], False, "none", 0, 0),
                 ex(a2["id"], b["id"], True, "indirect_specific", 1, 1, spec=True)]

        # T4 (N1): bare agreement; A2 other branch -> tie
        a1, a2 = mk(f"a1d_{k}", press, 100, hops=1), mk(f"a2d_{k}", cost, 110)
        b = mk(f"b4_{k}", "Tôi đồng ý.", 200, parent=a1["id"])
        add("T4", a1, a2, b, "tie", ["echo"])
        exts += [ex(a1["id"], b["id"], False, "none", 0, 0), ex(a2["id"], b["id"], False, "none", 0, 0)]

        # T5 (P2): disagree but uses the premise; A2 other branch
        a1, a2 = mk(f"a1e_{k}", press, 100, hops=1), mk(f"a2e_{k}", similar, 110)
        b = mk(f"b5_{k}", f"Không đúng, áp lực tâm lý này chưa chắc làm giảm kết quả vì các em đã chuẩn bị cho {tp}.", 200,
               parent=a1["id"])
        add("T5", a1, a2, b, "A1>A2", ["opposite_stance"])
        exts += [ex(a1["id"], b["id"], True, "direct_reply_premise", 1, 1), ex(a2["id"], b["id"], False, "none", 0, 0)]

        # T6: both pass the gate; A1 keeps only part of the frame (0.8*0.5=0.4), A2 named premise full (1.0)
        a1, a2 = mk(f"a1f_{k}", press, 100, hops=1), mk(f"a2f_{k}", f"{tp} làm học sinh mất ngủ.", 110, hops=1)
        b = mk(f"b6_{k}", f"Mất ngủ vì {tp} kéo theo kiệt sức và điểm kém.", 200, parent=a2["id"],
               quotes=[f"{tp} làm học sinh mất ngủ."])
        add("T6", a1, a2, b, "A1<A2", ["partial_frame"])
        exts += [ex(a1["id"], b["id"], True, "direct_reply_premise", 1, 0.5),
                 ex(a2["id"], b["id"], True, "named_premise", 1, 1)]
    return items, exts


def run(*args):
    print("$", " ".join(args))
    command = list(args)
    script = Path(command[0])
    if not script.is_absolute():
        command[0] = str(HERE / script)
    r = subprocess.run([sys.executable, *command], capture_output=True, text=True)
    print(r.stdout)
    if r.returncode:
        print(r.stderr)
        raise SystemExit(r.returncode)
    return r.stdout


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    items, exts = build()
    with open(OUT / "all.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in items)
    with open(OUT / "extractions.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in exts)

    loaded = load_items(str(OUT / "all.jsonl"))
    assert all("leak" not in [c.id for c in it.visible_context()] for it in loaded), "look-ahead leak"

    run("evaluate.py", "split", "--items", str(OUT / "all.jsonl"), "--out", str(OUT / "split"))
    run("llm.py", "extract", "--items", str(OUT / "all.jsonl"), "--out", str(OUT / "extractions_mock.jsonl"),
        "--model", "mock")
    out = run("evaluate.py", "eval", "--items", str(OUT / "all.jsonl"),
              "--extractions", str(OUT / "extractions.jsonl"),
              "--methods", "random,cosine,reply_quote,llm,proposed,proposed_u_only,proposed_d_only,"
                           "proposed_ungated,proposed_dmean",
              "--llm-model", "mock", "--reference", "cosine", "--boot", "500", "--out", str(OUT / "results"))
    print("OK: pipeline ran end to end")
