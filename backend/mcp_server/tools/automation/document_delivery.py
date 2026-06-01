"""文书送达自动下载 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def query_document_delivery(
    credential_id: int,
    cutoff_hours: int = 24,
    tab: str = "pending",
) -> dict[str, Any]:
    """手动触发文书查询和下载。tab 可选：pending（待查阅）或 reviewed（已查阅）；cutoff_hours 为只处理最近N小时内的文书。"""
    return client.post(
        "/automation/document-delivery/query",
        json={"credential_id": credential_id, "cutoff_hours": cutoff_hours, "tab": tab},
    )  # type: ignore[return-value]


def list_delivery_schedules(
    credential_id: int | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """查询文书送达定时任务列表。"""
    params: dict[str, Any] = {}
    if credential_id is not None:
        params["credential_id"] = credential_id
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/automation/document-delivery/schedules", params=params)  # type: ignore[return-value]


def create_delivery_schedule(
    credential_id: int,
    runs_per_day: int = 1,
    hour_interval: int = 24,
    cutoff_hours: int = 24,
    is_active: bool = True,
) -> dict[str, Any]:
    """创建文书送达定时任务。runs_per_day 为每天运行次数；hour_interval 为运行间隔（小时）。"""
    return client.post(
        "/automation/document-delivery/schedules",
        json={
            "credential_id": credential_id,
            "runs_per_day": runs_per_day,
            "hour_interval": hour_interval,
            "cutoff_hours": cutoff_hours,
            "is_active": is_active,
        },
    )  # type: ignore[return-value]
