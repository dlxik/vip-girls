from __future__ import annotations

from typing import Any

from bluesky.v2.explanation import concise_step_log


def society_step_log(step: dict[str, Any]) -> list[str]:
    lines = concise_step_log(step)
    prefix = f"[{step['timestamp']}:k{step['deliberation_step']}]"
    semantics = step["argumentation_semantics"]
    lines.append(
        f"{prefix} SEMANTICS {semantics['method']} iterations={semantics['iterations']} "
        f"converged={semantics['converged']}"
    )
    metrics = step["society_metrics_v3"]
    lines.append(
        f"{prefix} SOCIETY dominant={metrics['dominant_viewpoint']} "
        f"convergence_proxy={metrics['convergence_proxy']:.4f} "
        f"fragmentation_proxy={metrics['fragmentation_proxy']:.4f}"
    )
    for event in step["society_events"]:
        lines.append(
            f"{prefix} EVENT {event['event_type']} agents={','.join(event['involved_agents']) or '-'}"
        )
    return lines


def conflict_explanation(public_id: str, reference_id: str | None, score: float, relation_ids: list[str]) -> str:
    fact = (
        f"DỮ KIỆN: quan hệ tấn công chính tắc {','.join(relation_ids)} nối {public_id} với {reference_id}."
        if relation_ids else f"DỮ KIỆN: chưa ghi nhận quan hệ tấn công chính tắc từ {public_id} tới A_K đủ điều kiện."
    )
    return (
        f"{fact} MÔ HÌNH: C={score:.4f} là điểm cặp có căn cứ cao nhất trong H. "
        "GIỚI HẠN: không tự suy diễn mâu thuẫn chỉ từ văn bản."
    )


def steering_explanation(argument_id: str, score: float, downstream_count: int) -> str:
    return (
        f"DỮ KIỆN: {argument_id} xuất hiện trước và có liên kết quan sát được với {downstream_count} lập luận A_D phía sau. "
        f"MÔ HÌNH: chỉ báo định hướng đầu ra đã chuẩn hóa S={score:.4f}. "
        "GIỚI HẠN: thứ tự thời gian và liên kết cấu trúc không chứng minh ảnh hưởng nhân quả."
    )


def risk_explanation(argument_id: str, conflict: float, steering: float, risk: float) -> str:
    return (
        f"DỮ KIỆN: vết mô phỏng cung cấp bằng chứng xung đột/liên kết chính tắc cho {argument_id}. "
        f"MÔ HÌNH: hàm f(C,S) theo cấu hình ánh xạ C={conflict:.4f}, S={steering:.4f} thành RS={risk:.4f}. "
        "GIỚI HẠN: RS chỉ ưu tiên việc rà soát, không xác lập mức độ gây hại thực tế."
    )


def priority_explanation(argument_id: str, rank: int, risk: float) -> str:
    return (
        f"MÔ HÌNH: {argument_id} đứng ưu tiên {rank} khi sắp RS={risk:.4f} giảm dần "
        "và dùng mã lập luận để phá hòa. GIỚI HẠN: thứ hạng phụ thuộc cấu hình."
    )


def alert_explanation(alert_type: str, current: float, previous: float | None, threshold: float) -> str:
    prior = "chưa có" if previous is None else f"{previous:.4f}"
    return (
        f"MÔ HÌNH: {alert_type} được kích hoạt với giá trị trước={prior}, hiện tại={current:.4f}, "
        f"ngưỡng cấu hình={threshold:.4f}. GIỚI HẠN: đây là cảnh báo mô hình tất định, không phải khẳng định về một sự cố thực tế."
    )
