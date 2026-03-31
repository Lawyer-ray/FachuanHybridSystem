"""催收提醒 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_all_reminders(
    contract_id: int | None = None,
    case_log_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询提醒列表。可按合同ID（contract_id）或案件日志ID（case_log_id）筛选。"""
    params: dict[str, Any] = {}
    if contract_id is not None:
        params["contract_id"] = contract_id
    if case_log_id is not None:
        params["case_log_id"] = case_log_id
    return client.get("/reminders/list", params=params)  # type: ignore[return-value]


def get_reminder(reminder_id: int) -> dict[str, Any]:
    """获取单个提醒详情。"""
    return client.get(f"/reminders/{reminder_id}")  # type: ignore[return-value]


def create_new_reminder(
    reminder_type: str,
    content: str,
    due_at: str,
    contract_id: int | None = None,
    case_log_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建提醒。due_at 为到期时间（ISO格式如 2026-03-15T10:00:00）；reminder_type 常用值：call（电话）、visit（上门）、letter（律师函）。"""
    payload: dict[str, Any] = {
        "reminder_type": reminder_type,
        "content": content,
        "due_at": due_at,
    }
    if contract_id is not None:
        payload["contract_id"] = contract_id
    if case_log_id is not None:
        payload["case_log_id"] = case_log_id
    if metadata is not None:
        payload["metadata"] = metadata
    return client.post("/reminders/create", json=payload)  # type: ignore[return-value]


def update_reminder(
    reminder_id: int,
    reminder_type: str | None = None,
    content: str | None = None,
    due_at: str | None = None,
    is_done: bool | None = None,
) -> dict[str, Any]:
    """更新提醒信息。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if reminder_type is not None:
        payload["reminder_type"] = reminder_type
    if content is not None:
        payload["content"] = content
    if due_at is not None:
        payload["due_at"] = due_at
    if is_done is not None:
        payload["is_done"] = is_done
    return client.put(f"/reminders/{reminder_id}", json=payload)  # type: ignore[return-value]


def delete_reminder(reminder_id: int) -> None:
    """删除提醒。"""
    client.delete(f"/reminders/{reminder_id}")


def list_reminder_types() -> list[dict[str, Any]]:
    """获取所有支持的提醒类型列表。"""
    return client.get("/reminders/types")  # type: ignore[return-value]
