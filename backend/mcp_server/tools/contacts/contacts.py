"""联系人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_contacts(case_id: int | None = None, stage: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """获取案件联系人列表，可按案件ID和阶段筛选。

    limit 默认 50——REST 端点默认 1000 是给前端表格的,对模型上下文过大;
    truncated=true 时用 offset 续取(第 N 页传 offset=N×limit),或换更窄筛选。

    Args:
        case_id: 按案件筛选。
        stage: 按诉讼阶段筛选(如 一审/二审/执行)。
        limit: 最多返回条数(默认 50)。
        offset: 跳过前 offset 条再取——续取翻页用。
    """
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}  # limit+1 探测:知还有更多
    if case_id is not None:
        params["case_id"] = case_id
    if stage is not None:
        params["stage"] = stage
    return list_result(client.get("/contacts/contacts", params=params), limit=limit)


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
    """创建案件联系人（姓名/角色/法院等,便于后续案件快速引用）。

    Args:
        case_id: 关联案件 ID。
        name: 联系人姓名。
        role: 角色——法官/书记员/对方代理人/鉴定人等自由文本。
        authority_id: 所属法院/机构 ID(可经 search_contacts 的 court 筛选或法院列表工具查)。
        phone: 联系电话。
        address: 地址。
        stage: 诉讼阶段(如一审/二审/执行)。
        note: 备注。
    """
    return client.post(  # type: ignore[no-any-return]
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
    )


def search_contacts(q: str | None = None, court: str | None = None, role: str | None = None) -> dict[str, Any]:
    """公开搜索联系人库,按姓名、法院和角色筛选——跨案件复用联系人。

    Args:
        q: 姓名关键词(模糊匹配)。
        court: 法院名称关键词。
        role: 角色关键词(如 法官/书记员)。
    """
    params: dict[str, Any] = {}
    if q is not None:
        params["q"] = q
    if court is not None:
        params["court"] = court
    if role is not None:
        params["role"] = role
    return list_result(client.get("/contacts/contacts/search", params=params))


def get_contact(contact_id: int) -> dict[str, Any]:
    """获取单个联系人详情。"""
    return client.get(f"/contacts/contacts/{contact_id}")  # type: ignore[no-any-return]


def update_contact(contact_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新联系人信息。只传需要修改的字段。"""
    return client.put(f"/contacts/contacts/{contact_id}", json=fields or {})  # type: ignore[no-any-return]


def delete_contact(contact_id: int) -> None:
    """删除联系人——硬删除,不可恢复。"""
    client.delete(f"/contacts/contacts/{contact_id}")
