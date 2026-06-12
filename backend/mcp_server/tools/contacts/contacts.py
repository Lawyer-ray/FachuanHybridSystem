"""联系人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_contacts(case_id: int | None = None, stage: str | None = None) -> list[dict[str, Any]]:
    """获取案件联系人列表，可按案件ID和阶段筛选。"""
    params: dict[str, Any] = {}
    if case_id is not None:
        params["case_id"] = case_id
    if stage is not None:
        params["stage"] = stage
    return client.get("/contacts/contacts", params=params)  # type: ignore[return-value]


def create_contact(
    case_id: int,
    name: str,
    role: str,
    authority_id: int | None = None,
    phone: str | None = None,
    address: str | None = None,
    stage: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """创建案件联系人。"""
    return client.post(
        "/contacts/contacts",
        json={
            "case_id": case_id,
            "name": name,
            "role": role,
            "authority_id": authority_id,
            "phone": phone,
            "address": address,
            "stage": stage,
            "note": note,
        },
    )  # type: ignore[return-value]


def search_contacts(q: str | None = None, court: str | None = None, role: str | None = None) -> list[dict[str, Any]]:
    """公开搜索联系人，按姓名、法院和角色筛选。"""
    params: dict[str, Any] = {}
    if q is not None:
        params["q"] = q
    if court is not None:
        params["court"] = court
    if role is not None:
        params["role"] = role
    return client.get("/contacts/contacts/search", params=params)  # type: ignore[return-value]


def get_contact(contact_id: int) -> dict[str, Any]:
    """获取单个联系人详情。"""
    return client.get(f"/contacts/contacts/{contact_id}")  # type: ignore[return-value]


def update_contact(contact_id: int, **fields: Any) -> dict[str, Any]:
    """更新联系人信息。"""
    return client.put(f"/contacts/contacts/{contact_id}", json=fields)  # type: ignore[return-value]


def delete_contact(contact_id: int) -> None:
    """删除联系人。"""
    client.delete(f"/contacts/contacts/{contact_id}")
