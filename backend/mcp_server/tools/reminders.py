"""催收提醒 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_reminders(
    reminder_type: str | None = None,
    is_done: bool | None = None,
) -> list[dict[str, Any]]:
    """查询催收提醒列表。reminder_type 为提醒类型；is_done=False 查询未完成的待办。"""
    params: dict[str, Any] = {}
    if reminder_type:
        params["reminder_type"] = reminder_type
    if is_done is not None:
        params["is_done"] = is_done
    return client.get("/reminders/list", params=params)  # type: ignore[return-value]
