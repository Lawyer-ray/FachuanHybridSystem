"""OA 客户导入 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def trigger_client_import(
    headless: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """触发从 OA 系统导入客户。headless=True 为无头浏览器模式；limit 为最大导入数量（None 表示全量）。返回 session_id 用于查询进度。"""
    payload: dict[str, Any] = {"headless": headless}
    if limit is not None:
        payload["limit"] = limit
    return client.post("/client-import", json=payload)  # type: ignore[return-value]


def get_client_import_session(session_id: int) -> dict[str, Any]:
    """查询客户导入会话状态。status: pending/running/completed/failed。"""
    return client.get(f"/client-import/{session_id}")  # type: ignore[return-value]
