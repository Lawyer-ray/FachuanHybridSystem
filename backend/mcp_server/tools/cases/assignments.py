"""律师指派 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_case_assignments(case_id: int) -> dict[str, Any]:
    """查询案件的律师指派记录（谁在何时以什么角色办案）。"""
    return list_result(client.get("/cases/assignments", params={"case_id": case_id}))


def assign_lawyer(case_id: int, lawyer_id: int) -> dict[str, Any]:
    """为案件指派办案律师（role 如主办/协办）。同一律师可多条记录。"""
    return client.post("/cases/assignments", json={"case_id": case_id, "lawyer_id": lawyer_id})  # type: ignore[no-any-return]


def get_case_assignment(assignment_id: int) -> dict[str, Any]:
    """获取单条律师指派记录详情（律师、角色、指派时间）。"""
    return client.get(f"/cases/assignments/{assignment_id}")  # type: ignore[no-any-return]


def update_case_assignment(assignment_id: int, lawyer_id: int | None = None) -> dict[str, Any]:
    """更新律师指派（换律师）。只传需要修改的字段。

    指派记录没有可改的角色字段——旧签名的 ``role`` 参数从未生效
    （端点 ``CaseAssignmentUpdate`` 只声明 case_id/lawyer_id,2026-10-25 移除）。
    """
    payload: dict[str, Any] = {}
    if lawyer_id is not None:
        payload["lawyer_id"] = lawyer_id
    return client.put(f"/cases/assignments/{assignment_id}", json=payload)  # type: ignore[no-any-return]


def delete_case_assignment(assignment_id: int) -> None:
    """删除一条律师指派记录——硬删除,不可恢复（不影响案件本身）。"""
    client.delete(f"/cases/assignments/{assignment_id}")
