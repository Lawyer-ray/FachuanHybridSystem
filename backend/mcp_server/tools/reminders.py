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


def create_reminder(
    reminder_type: str,
    content: str,
    due_at: str,
    contract_id: int | None = None,
    case_log_id: int | None = None,
) -> dict[str, Any]:
    """创建催收提醒。due_at 为到期时间（ISO 格式如 2026-03-15T10:00:00）；reminder_type 常用值：call（电话）、visit（上门）、letter（律师函）。"""
    payload: dict[str, Any] = {"reminder_type": reminder_type, "content": content, "due_at": due_at}
    if contract_id is not None:
        payload["contract_id"] = contract_id
    if case_log_id is not None:
        payload["case_log_id"] = case_log_id
    return client.post("/reminders/create", json=payload)  # type: ignore[return-value]
