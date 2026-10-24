"""案件当事人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_parties(case_id: int) -> list[dict[str, Any]]:
    """查询指定案件的所有当事人，包含客户详情和诉讼地位。

    后端 ``/cases/parties`` 声明 ``response=list[CasePartyOut]``，返回裸数组。
    早前这里声明 ``dict`` 并用 ``as_items`` 包一层分页壳，但那只是掩盖了
    类型不符（分页壳里的 ``items`` 是模型永远看不到的假结构）。
    """
    return client.get("/cases/parties", params={"case_id": case_id})  # type: ignore[return-value]


def add_case_party(case_id: int, client_id: int, legal_status: str | None = None) -> dict[str, Any]:
    """为案件添加当事人。legal_status 为诉讼地位，如：原告、被告、第三人等。"""
    payload: dict[str, Any] = {"case_id": case_id, "client_id": client_id}
    if legal_status:
        payload["legal_status"] = legal_status
    return client.post("/cases/parties", json=payload)  # type: ignore[return-value]


def get_case_party(party_id: int) -> dict[str, Any]:
    """获取单个当事人的详情（身份、诉讼地位、联系方式）。"""
    return client.get(f"/cases/parties/{party_id}")  # type: ignore[return-value]


def update_case_party(
    party_id: int, legal_status: str | None = None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """更新当事人信息（姓名/诉讼地位/证件等）。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if legal_status is not None:
        payload["legal_status"] = legal_status
    payload.update(extra)
    return client.put(f"/cases/parties/{party_id}", json=payload)  # type: ignore[return-value]


def delete_case_party(party_id: int) -> None:
    """把当事人从案件中移除——硬删除该关联记录,不可恢复。"""
    client.delete(f"/cases/parties/{party_id}")
