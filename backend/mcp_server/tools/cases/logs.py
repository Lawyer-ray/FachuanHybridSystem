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
