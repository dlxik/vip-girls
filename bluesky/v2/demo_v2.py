from __future__ import annotations

import argparse
import hashlib
import json
import webbrowser
from pathlib import Path

from bluesky.src.loader import load_ctq_data, repository_root
from bluesky.src.temporal_graph import build_temporal_snapshots
from bluesky.src.viewpoint import add_viewpoint_layers

from .simulation import AutonomousArgumentationSimulation
from .validation import validate_trace_provenance
from .visualizer_v2 import render_v2_html


def _write_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _canonical_input_hashes(root: Path) -> dict[str, str]:
    relative_paths = (
        "data/timelines/ctq_timeline.csv",
        "data/annotations/ctq_selected_arguments.csv",
        "data/annotations/ctq_arguments.csv",
        "data/annotations/ctq_argument_status.csv",
        "data/annotations/ctq_relations.csv",
        "data/sources/ctq_sources.csv",
        "bluesky/data/viewpoint_mapping.json",
    )
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in relative_paths
    }


def build_v2_outputs(verbose: bool = False) -> tuple[dict, Path, Path]:
    data = load_ctq_data()
    snapshots = build_temporal_snapshots(data)
    add_viewpoint_layers(snapshots, data["viewpoint_mapping"])
    trace = AutonomousArgumentationSimulation(data, snapshots).run(verbose=verbose)
    trace["provenance_validation"] = validate_trace_provenance(trace, data, snapshots)
    root = repository_root()
    trace["canonical_input_sha256"] = _canonical_input_hashes(root)
    trace_path = _write_json(trace, root / "bluesky/outputs/v2_simulation_trace.json")
    html_path = render_v2_html(
        trace, data["viewpoint_mapping"], root / "bluesky/outputs/autonomous_agent_demo_v2.html"
    )
    return trace, trace_path, html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy AGORA V2 autonomous argumentative-agent simulation")
    parser.add_argument("--open", action="store_true", help="Mở HTML sau khi sinh")
    parser.add_argument("--verbose", action="store_true", help="In deterministic simulation log")
    args = parser.parse_args()
    trace, trace_path, html_path = build_v2_outputs(verbose=args.verbose)
    print("AGORA V2 - autonomous argumentative agents")
    print("=" * 50)
    for run in trace["timestamps"]:
        action_count = sum(len(step["interactions"]) for step in run["steps"])
        revision_count = sum(len(step["belief_revisions"]) for step in run["steps"])
        print(
            f"{run['timestamp']}: k={run['steps_executed']}, actions={action_count}, "
            f"revisions={revision_count}, stop={run['stop_reason']}"
        )
    print(f"\nTrace: {trace_path}")
    print(f"Visualization: {html_path}")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())


if __name__ == "__main__":
    main()
