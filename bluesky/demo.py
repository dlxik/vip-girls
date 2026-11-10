from __future__ import annotations

import argparse
import webbrowser

from .src.loader import load_ctq_data, repository_root
from .src.temporal_graph import build_temporal_snapshots
from .src.viewpoint import add_viewpoint_layers
from .src.visualizer import render_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh demo temporal CTQ của AGORA Blue Sky")
    parser.add_argument("--open", action="store_true", help="Mở HTML sau khi sinh")
    args = parser.parse_args()

    data = load_ctq_data()
    snapshots = build_temporal_snapshots(data)
    add_viewpoint_layers(snapshots, data["viewpoint_mapping"])
    output = render_html(
        snapshots,
        data["viewpoint_mapping"],
        repository_root() / "bluesky/outputs/temporal_agentic_demo.html",
    )

    print("AGORA Blue Sky - CTQ temporal argument graph")
    print("=" * 52)
    for snapshot in snapshots:
        timestamp_id = snapshot["timestamp"]["timestamp_id"]
        print(
            f"{timestamp_id}: arguments={len(snapshot['arguments'])}, "
            f"relations={len(snapshot['relations'])}, "
            f"viewpoints={len(snapshot['viewpoints'])}"
        )
    print(f"\nVisualization written to: {output}")
    if args.open:
        webbrowser.open(output.resolve().as_uri())


if __name__ == "__main__":
    main()
