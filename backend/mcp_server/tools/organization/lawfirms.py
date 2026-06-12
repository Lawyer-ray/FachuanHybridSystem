"""律所管理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_lawfirms(name: str | None = None) -> list[dict[str, Any]]:
    """查询律所列表。可按名称（name）模糊搜索。"""
    params: dict[str, Any] = {}
    if name:
        params["name"] = name
    return client.get("/organization/lawfirms", params=params)  # type: ignore[return-value]


def get_lawfirm(law_firm_id: int) -> dict[str, Any]:
    """获取单个律所的详细信息。"""
    return client.get(f"/organization/lawfirms/{law_firm_id}")  # type: ignore[return-value]


def create_lawfirm(
    name: str,
    address: str | None = None,
    phone: str | None = None,
    social_credit_code: str | None = None,
) -> dict[str, Any]:
    """创建新律所。name 必填；social_credit_code 为统一社会信用代码。"""
    payload: dict[str, Any] = {"name": name}
    if address:
        payload["address"] = address
    if phone:
        payload["phone"] = phone
    if social_credit_code:
        payload["social_credit_code"] = social_credit_code
    return client.post("/organization/lawfirms", json=payload)  # type: ignore[return-value]


def update_lawfirm(
    law_firm_id: int,
    name: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    social_credit_code: str | None = None,
) -> dict[str, Any]:
    """更新律所信息。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if address is not None:
        payload["address"] = address
    if phone is not None:
        payload["phone"] = phone
    if social_credit_code is not None:
        payload["social_credit_code"] = social_credit_code
    return client.put(f"/organization/lawfirms/{law_firm_id}", json=payload)  # type: ignore[return-value]


def delete_lawfirm(law_firm_id: int) -> None:
    """删除指定律所。此操作不可逆。"""
    client.delete(f"/organization/lawfirms/{law_firm_id}")
