"""Streamlit viewer for WSDM experiment run directories."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "wsdm" / "results"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def csv_bytes(records):
    output = io.StringIO()
    columns = [
        "item_id", "thread_id", "label", "slice", "method", "score_A1", "score_A2",
        "predicted_higher", "A1_id", "A2_id", "B_id",
    ]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for record in records:
        for method, result in record["methods"].items():
            writer.writerow({
                "item_id": record["item_id"], "thread_id": record["thread_id"],
                "label": record["label"], "slice": ";".join(record.get("slices", [])),
                "method": method, "score_A1": result["score_A1"],
                "score_A2": result["score_A2"],
                "predicted_higher": result["predicted_higher"],
                "A1_id": record["candidates"]["A1"]["id"],
                "A2_id": record["candidates"]["A2"]["id"], "B_id": record["B"]["id"],
            })
    return output.getvalue().encode("utf-8-sig")


def relation(candidate):
    hops = candidate.get("hops")
    if hops == 1:
        return "direct parent (1 reply hop)"
    if hops:
        return f"ancestor ({hops} reply hops)"
    return "different branch / no ancestor path"


def component_table(result):
    rows = []
    for key in ("A1", "A2"):
        explanation = result.get(f"explain_{key}", {})
        components = explanation.get("components", {})
        rows.append({
            "candidate": key, "G": components.get("G"), "U": components.get("U_raw"),
            "d_aspect": components.get("d_aspect"), "d_lens": components.get("d_lens"),
            "D_min": components.get("D"), "trace": ", ".join(components.get("trace", [])),
            "span_pair_ok": components.get("span_pair_ok"),
            "has_extraction": components.get("has_extraction"),
        })
    return rows


st.set_page_config(page_title="WSDM Steering Viewer", layout="wide")
st.title("WSDM Argumentative Steering — local experiment viewer")

runs = sorted(
    [path.parent for path in RESULTS.glob("*/manifest.json") if (path.parent / "predictions.jsonl").is_file()],
    reverse=True,
)
if not runs:
    st.warning(f"No experiment runs found under {RESULTS}. Run wsdm/run_experiment.py first.")
    st.stop()

selected_name = st.sidebar.selectbox("Experiment run", [run.name for run in runs])
run_dir = next(run for run in runs if run.name == selected_name)
manifest = read_json(run_dir / "manifest.json")
summary = read_json(run_dir / "summary.json")
records = read_jsonl(run_dir / "predictions.jsonl")

status = summary.get("status", "UNKNOWN")
if "GOLD" not in status:
    st.warning(f"{status}: {summary.get('scientific_claim', 'No gold evaluation available.')}")
else:
    st.success(status)

methods = summary.get("methods", [])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Items", summary.get("n_items", len(records)))
c2.metric("Threads", summary.get("n_threads", len({r['thread_id'] for r in records})))
c3.metric("Methods", len(methods))
c4.metric("Missing extractions", summary.get("missing_extraction_pairs", 0))
st.caption(
    f"Source: {manifest.get('source_items')} · Model: {manifest.get('model') or 'none'} · "
    f"Created: {manifest.get('created_at')}"
)

st.sidebar.subheader("Filters")
hard_negative = st.sidebar.checkbox("Hard negatives only")
disagreement = st.sidebar.checkbox("Baseline/proposed disagreements")
zero_scores = st.sidebar.checkbox("Zero-score cases")
selected_method = st.sidebar.selectbox("Score method", methods)

filtered = records
if hard_negative:
    filtered = [
        record for record in filtered
        if any("other" in tag or "ancestor" in tag for tag in record.get("slices", []))
    ]
if disagreement:
    filtered = [
        record for record in filtered
        if "cosine" in record["methods"] and "proposed" in record["methods"]
        and record["methods"]["cosine"]["predicted_higher"]
        != record["methods"]["proposed"]["predicted_higher"]
    ]
if zero_scores:
    filtered = [
        record for record in filtered
        if record["methods"][selected_method]["score_A1"] == 0
        or record["methods"][selected_method]["score_A2"] == 0
    ]

st.download_button(
    "Export filtered predictions to CSV", csv_bytes(filtered),
    file_name=f"{selected_name}_predictions.csv", mime="text/csv",
)
if not filtered:
    st.info("No items match the current filters.")
    st.stop()

item_id = st.selectbox("Item", [record["item_id"] for record in filtered])
record = next(record for record in filtered if record["item_id"] == item_id)
st.subheader(f"B — {record['B']['id']}")
st.caption(
    f"thread={record['thread_id']} · timestamp={record['B']['timestamp']} · "
    f"parent={record['B'].get('parent_id')} · label={record['label'].upper()} · "
    f"slices={', '.join(record.get('slices', []))}"
)
st.write(record["B"]["text"])
if record["B"].get("quotes"):
    st.markdown("**B quotes:** " + " | ".join(record["B"]["quotes"]))

left, right = st.columns(2)
for column, key in ((left, "A1"), (right, "A2")):
    candidate = record["candidates"][key]
    with column:
        st.subheader(f"{key} — {candidate['id']}")
        st.caption(
            f"timestamp={candidate['timestamp']} · {relation(candidate)} · "
            f"parent={candidate.get('parent_id')}"
        )
        st.write(candidate["text"])

score_rows = []
for method, result in record["methods"].items():
    score_rows.append({
        "method": method, "A1": result["score_A1"], "A2": result["score_A2"],
        "prediction": result["predicted_higher"],
    })
st.subheader("Method comparison")
st.dataframe(score_rows, use_container_width=True, hide_index=True)

result = record["methods"][selected_method]
if selected_method.startswith("proposed"):
    st.subheader(f"Extraction components — {selected_method}")
    st.dataframe(component_table(result), use_container_width=True, hide_index=True)
    a1, a2 = st.columns(2)
    for column, key in ((a1, "A1"), (a2, "A2")):
        explanation = result.get(f"explain_{key}", {})
        with column:
            st.markdown(f"**{key} evidence spans**")
            st.write("A span:", explanation.get("span_A") or "—")
            st.write("B span:", explanation.get("span_B") or "—")
            st.write("Frame A:", explanation.get("frame_A") or "—")
            st.write("Frame B:", explanation.get("frame_B") or "—")
            if explanation.get("reason"):
                st.info(explanation["reason"])

if "evaluation" in summary:
    st.subheader("Evaluation")
    st.dataframe(summary["evaluation"], use_container_width=True)
else:
    st.info("No evaluation table: this run has no independently reviewed ranking gold labels.")
