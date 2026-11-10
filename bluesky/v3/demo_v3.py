from __future__ import annotations

import argparse
import hashlib
import json
import webbrowser
from pathlib import Path

from bluesky.src.loader import load_ctq_data, repository_root
from bluesky.src.temporal_graph import build_temporal_snapshots
from bluesky.src.viewpoint import add_viewpoint_layers

from .config_v3 import DEFAULT_V3_CONFIG
from .evaluation import EvaluationRunner
from .simulation_v3 import DynamicSocietySimulation
from .validation_v3 import validate_v3_trace
from .visualizer_v3 import render_v3_html


CANONICAL_INPUTS = (
    "data/timelines/ctq_timeline.csv",
    "data/annotations/ctq_selected_arguments.csv",
    "data/annotations/ctq_arguments.csv",
    "data/annotations/ctq_argument_status.csv",
    "data/annotations/ctq_relations.csv",
    "data/sources/ctq_sources.csv",
    "bluesky/data/viewpoint_mapping.json",
)


def _hashes(root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in CANONICAL_INPUTS
    }


def _write_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_v3_outputs(
    verbose: bool = False,
    evaluation: bool = False,
) -> tuple[dict, Path, Path, Path | None]:
    root = repository_root()
    before = _hashes(root)
    data = load_ctq_data()
    snapshots = build_temporal_snapshots(data)
    add_viewpoint_layers(snapshots, data["viewpoint_mapping"])
    trace = DynamicSocietySimulation(data, snapshots, DEFAULT_V3_CONFIG).run(verbose=verbose)
    trace["provenance_validation"] = validate_v3_trace(trace, data, snapshots)
    after = _hashes(root)
    if before != after:
        raise RuntimeError("V3 đã làm thay đổi canonical input; dừng để bảo toàn dữ liệu.")
    trace["canonical_input_sha256"] = before
    trace["canonical_inputs_unchanged"] = True
    trace_path = _write_json(trace, root / "bluesky/outputs/v3_simulation_trace.json")
    html_path = render_v3_html(
        trace, data["viewpoint_mapping"], root / "bluesky/outputs/dynamic_agent_society_v3.html"
    )
    evaluation_path = None
    if evaluation:
        report = EvaluationRunner(data, snapshots).run(DEFAULT_V3_CONFIG)
        evaluation_path = _write_json(
            report, root / "bluesky/outputs/v3_evaluation_report.json"
        )
    return trace, trace_path, html_path, evaluation_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy AGORA V3 Dynamic Agent Society")
    parser.add_argument("--open", action="store_true", help="Mở HTML sau khi sinh")
    parser.add_argument("--verbose", action="store_true", help="In deterministic V3 log")
    parser.add_argument("--evaluation", action="store_true", help="Chạy sensitivity + ablation report")
    args = parser.parse_args()
    trace, trace_path, html_path, evaluation_path = build_v3_outputs(
        verbose=args.verbose, evaluation=args.evaluation
    )
    print("AGORA V3 - Dynamic Agent Society")
    print("=" * 50)
    for run in trace["timestamps"]:
        events = sum(len(step["society_events"]) for step in run["steps"])
        final = run["steps"][-1]["society_metrics_v3"]
        print(
            f"{run['timestamp']}: k={run['steps_executed']}, events={events}, "
            f"dominant={final['dominant_viewpoint']}, stop={run['stop_reason']}"
        )
    print(f"\nTrace: {trace_path}")
    print(f"Visualization: {html_path}")
    if evaluation_path:
        print(f"Evaluation: {evaluation_path}")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())


if __name__ == "__main__":
    main()
