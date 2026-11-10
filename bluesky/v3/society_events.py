from __future__ import annotations

from typing import Any

from .models import SocietyEvent


def make_event(
    index: int,
    timestamp: str,
    deliberation_step: int,
    event_type: str,
    agents: list[str],
    arguments: list[str],
    metric_snapshot: dict[str, Any],
    threshold: dict[str, Any],
    explanation: str,
    provenance: dict[str, list[str]],
) -> SocietyEvent:
    return SocietyEvent(
        event_id=f"SE-{timestamp}-k{deliberation_step}-{index:03d}",
        timestamp=timestamp,
        deliberation_step=deliberation_step,
        event_type=event_type,
        involved_agents=sorted(set(agents)),
        involved_arguments=sorted(set(arguments)),
        metric_snapshot=metric_snapshot,
        threshold=threshold,
        explanation=explanation,
        provenance={key: sorted(set(value)) for key, value in provenance.items()},
    )
