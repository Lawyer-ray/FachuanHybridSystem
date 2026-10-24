"""律师指派 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_assignments(case_id: int) -> list[dict[str, Any]]:
    """查询案件的律师指派记录（谁在何时以什么角色办案）。"""
    return client.get("/cases/assignments", params={"case_id": case_id})  # type: ignore[return-value]


def assign_lawyer(case_id: int, lawyer_id: int) -> dict[str, Any]:
    """为案件指派办案律师（role 如主办/协办）。同一律师可多条记录。"""
    return client.post("/cases/assignments", json={"case_id": case_id, "lawyer_id": lawyer_id})  # type: ignore[return-value]


def get_case_assignment(assignment_id: int) -> dict[str, Any]:
    """获取单条律师指派记录详情（律师、角色、指派时间）。"""
    return client.get(f"/cases/assignments/{assignment_id}")  # type: ignore[return-value]


def update_case_assignment(assignment_id: int, lawyer_id: int | None = None, role: str | None = None) -> dict[str, Any]:
    """更新律师指派（改角色/换律师）。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if lawyer_id is not None:
        payload["lawyer_id"] = lawyer_id
    if role is not None:
        payload["role"] = role
    return client.put(f"/cases/assignments/{assignment_id}", json=payload)  # type: ignore[return-value]


def delete_case_assignment(assignment_id: int) -> None:
    """删除一条律师指派记录——硬删除,不可恢复（不影响案件本身）。"""
    client.delete(f"/cases/assignments/{assignment_id}")
