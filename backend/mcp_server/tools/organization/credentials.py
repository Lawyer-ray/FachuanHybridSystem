"""账号凭证 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_credentials(
    lawyer_id: int | None = None,
    lawyer_name: str | None = None,
) -> list[dict[str, Any]]:
    """查询账号凭证列表。可按律师 ID（lawyer_id）或律师姓名（lawyer_name）筛选。"""
    params: dict[str, Any] = {}
    if lawyer_id is not None:
        params["lawyer_id"] = lawyer_id
    if lawyer_name:
        params["lawyer_name"] = lawyer_name
    return client.get("/organization/credentials", params=params)  # type: ignore[return-value]


def get_credential(cred_id: int) -> dict[str, Any]:
    """获取单个账号凭证的详细信息。"""
    return client.get(f"/organization/credentials/{cred_id}")  # type: ignore[return-value]


def create_credential(
    lawyer_id: int,
    site_name: str,
    account: str,
    password: str,
    url: str | None = None,
) -> dict[str, Any]:
    """创建账号凭证。lawyer_id 关联律师；site_name 为系统名称（如 jczd、gsxt）；account 和 password 为登录凭据。"""
    payload: dict[str, Any] = {
        "lawyer_id": lawyer_id,
        "site_name": site_name,
        "account": account,
        "password": password,
    }
    if url:
        payload["url"] = url
    return client.post("/organization/credentials", json=payload)  # type: ignore[return-value]


def update_credential(
    cred_id: int,
    site_name: str | None = None,
    url: str | None = None,
    account: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """更新账号凭证。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if site_name is not None:
        payload["site_name"] = site_name
    if url is not None:
        payload["url"] = url
    if account is not None:
        payload["account"] = account
    if password is not None:
        payload["password"] = password
    return client.put(f"/organization/credentials/{cred_id}", json=payload)  # type: ignore[return-value]


def delete_credential(cred_id: int) -> None:
    """删除指定账号凭证。此操作不可逆。"""
    client.delete(f"/organization/credentials/{cred_id}")
