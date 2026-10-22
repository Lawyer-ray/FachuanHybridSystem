"""案件当事人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import as_items, client


def list_case_parties(case_id: int) -> dict[str, Any]:
    """查询指定案件的所有当事人，包含客户详情和诉讼地位。

    返回分页结构 ``{items, total, page, page_size}``（REST 端点返回分页 dict，
    早期声明为 ``list`` 会使 MCP 输出校验失败）。
    """
    return as_items(client.get("/cases/parties", params={"case_id": case_id}))


def add_case_party(case_id: int, client_id: int, legal_status: str | None = None) -> dict[str, Any]:
    """为案件添加当事人。legal_status 为诉讼地位，如：原告、被告、第三人等。"""
    payload: dict[str, Any] = {"case_id": case_id, "client_id": client_id}
    if legal_status:
        payload["legal_status"] = legal_status
    return client.post("/cases/parties", json=payload)  # type: ignore[return-value]


def get_case_party(party_id: int) -> dict[str, Any]:
    """获取单个案件当事人详情。"""
    return client.get(f"/cases/parties/{party_id}")  # type: ignore[return-value]


def update_case_party(party_id: int, legal_status: str | None = None, **extra: Any) -> dict[str, Any]:
    """更新案件当事人信息。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if legal_status is not None:
        payload["legal_status"] = legal_status
    payload.update(extra)
    return client.put(f"/cases/parties/{party_id}", json=payload)  # type: ignore[return-value]


def delete_case_party(party_id: int) -> None:
    """从案件中移除当事人。"""
    client.delete(f"/cases/parties/{party_id}")
