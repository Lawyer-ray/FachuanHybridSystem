"""案件进展日志 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_logs(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有进展日志，按时间倒序排列。"""
    return client.get("/cases/logs", params={"case_id": case_id})  # type: ignore[return-value]


def create_case_log(case_id: int, content: str) -> dict[str, Any]:
    """为案件添加进展日志。content 为日志内容，支持多行文本。"""
    return client.post("/cases/logs", json={"case_id": case_id, "content": content})  # type: ignore[return-value]


def get_case_log(log_id: int) -> dict[str, Any]:
    """获取单条案件日志详情。"""
    return client.get(f"/cases/logs/{log_id}")  # type: ignore[return-value]


def update_case_log(log_id: int, content: str | None = None) -> dict[str, Any]:
    """更新案件日志内容。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    return client.put(f"/cases/logs/{log_id}", json=payload)  # type: ignore[return-value]


def delete_case_log(log_id: int) -> None:
    """删除案件日志。此操作不可逆。"""
    client.delete(f"/cases/logs/{log_id}")
