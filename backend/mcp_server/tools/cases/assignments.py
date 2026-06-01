"""律师指派 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_assignments(case_id: int) -> list[dict[str, Any]]:
    """查询案件的律师指派记录。"""
    return client.get("/cases/assignments", params={"case_id": case_id})  # type: ignore[return-value]


def assign_lawyer(case_id: int, lawyer_id: int) -> dict[str, Any]:
    """为案件指派律师。"""
    return client.post("/cases/assignments", json={"case_id": case_id, "lawyer_id": lawyer_id})  # type: ignore[return-value]
