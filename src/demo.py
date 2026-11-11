from __future__ import annotations

import argparse
import hashlib
import json
import webbrowser
from pathlib import Path

from hierarchy.config import DEFAULT_HIERARCHY_CONFIG
from hierarchy.evaluation import PropagationEvaluationRunner
from hierarchy.simulation import HierarchicalArgumentSocietySimulation
from hierarchy.validation import validate_hierarchy_trace
from hierarchy.visualizer import render_hierarchy_html
from pipeline.loader import load_ctq_data, repository_root
from pipeline.temporal_graph import build_temporal_snapshots
from pipeline.viewpoint import add_viewpoint_layers

CANONICAL_INPUTS = (
    "data/timelines/ctq_timeline.csv",
    "data/annotations/ctq_selected_arguments.csv",
    "data/annotations/ctq_arguments.csv",
    "data/annotations/ctq_argument_status.csv",
    "data/annotations/ctq_relations.csv",
    "data/sources/ctq_sources.csv",
    "src/resources/viewpoint_mapping.json",
)


def _hashes(root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in CANONICAL_INPUTS
    }


def _write_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return path


def build_outputs(
    verbose: bool = False,
    evaluation: bool = False,
) -> tuple[dict, Path, Path, Path | None]:
    root = repository_root()
    before = _hashes(root)
    data = load_ctq_data()
    snapshots = build_temporal_snapshots(data)
    add_viewpoint_layers(snapshots, data["viewpoint_mapping"])
    trace = HierarchicalArgumentSocietySimulation(
        data, snapshots, DEFAULT_HIERARCHY_CONFIG
    ).run(verbose=verbose)
    trace["provenance_validation"] = validate_hierarchy_trace(trace, data, snapshots)
    after = _hashes(root)
    if before != after:
        raise RuntimeError("Mô phỏng đã làm thay đổi canonical input; dừng để bảo toàn dữ liệu.")
    trace["canonical_input_sha256"] = before
    trace["canonical_inputs_unchanged"] = True
    trace_path = _write_json(trace, root / "outputs/simulation-trace.json")
    html_path = render_hierarchy_html(
        trace,
        data["viewpoint_mapping"],
        root / "outputs/index.html",
    )
    evaluation_path = None
    if evaluation:
        report = PropagationEvaluationRunner(data, snapshots).run()
        evaluation_path = _write_json(
            report, root / "outputs/evaluation-report.json"
        )
    return trace, trace_path, html_path, evaluation_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the VIP Girls hierarchical argumentative-agent simulation"
    )
    parser.add_argument("--open", action="store_true", help="Open the generated HTML")
    parser.add_argument("--verbose", action="store_true", help="Print the deterministic simulation log")
    parser.add_argument(
        "--evaluation",
        action="store_true",
        help="Compare zero-delay with fixed-delay=1k",
    )
    args = parser.parse_args()
    trace, trace_path, html_path, evaluation_path = build_outputs(
        verbose=args.verbose, evaluation=args.evaluation
    )
    print("VIP Girls - Hierarchical Argumentative Agent Society")
    print("=" * 58)
    print(f"Argument subagents: {len(trace['argument_subagents'])}")
    print(f"Messages: {len(trace['message_trace'])}")
    print(
        "Propagation: "
        f"{trace['propagation_assumption']['mode']} "
        f"({trace['propagation_assumption']['default_delay_steps']}k)"
    )
    print(f"Risk windows: {len(trace['risk_monitoring']['by_window'])}")
    print(f"Trace: {trace_path}")
    print(f"Visualization: {html_path}")
    if evaluation_path:
        print(f"Evaluation: {evaluation_path}")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())


if __name__ == "__main__":
    main()
