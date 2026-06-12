"""网上立案 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_court_filing_case_info(case_id: int) -> dict[str, Any]:
    """获取立案案件信息。"""
    return client.get(f"/automation/court-filing/case-info/{case_id}")  # type: ignore[return-value]


def get_court_filing_session(session_id: int) -> dict[str, Any]:
    """查询立案任务会话状态。"""
    return client.get(f"/automation/court-filing/session/{session_id}")  # type: ignore[return-value]


def execute_court_filing(case_id: int, **extra: Any) -> dict[str, Any]:
    """执行网上立案。case_id 为案件ID；其余参数通过 extra 透传。"""
    return client.post("/automation/court-filing/execute", json={"case_id": case_id, **extra})  # type: ignore[return-value]
