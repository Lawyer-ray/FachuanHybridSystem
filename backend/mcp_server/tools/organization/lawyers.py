"""律师管理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_lawyers(team_id: int | None = None) -> list[dict[str, Any]]:
    """查询律师列表。可按团队（team_id）筛选。返回律师 ID、姓名、团队等信息，用于指派律师时选择。"""
    params: dict[str, Any] = {}
    if team_id is not None:
        params["team_id"] = team_id
    return client.get("/organization/lawyers", params=params)  # type: ignore[return-value]


def get_lawyer(lawyer_id: int) -> dict[str, Any]:
    """获取单个律师的详细信息，包含律所、团队、执业证号等。"""
    return client.get(f"/organization/lawyers/{lawyer_id}")  # type: ignore[return-value]


def create_lawyer(
    username: str,
    password: str,
    real_name: str | None = None,
    phone: str | None = None,
    license_no: str | None = None,
    id_card: str | None = None,
    law_firm_id: int | None = None,
    is_admin: bool = False,
    lawyer_team_ids: list[int] | None = None,
    biz_team_ids: list[int] | None = None,
) -> dict[str, Any]:
    """创建新律师账号。username 和 password 必填；law_firm_id 关联律所；lawyer_team_ids 和 biz_team_ids 关联团队。"""
    payload: dict[str, Any] = {
        "username": username,
        "password": password,
        "is_admin": is_admin,
    }
    if real_name:
        payload["real_name"] = real_name
    if phone:
        payload["phone"] = phone
    if license_no:
        payload["license_no"] = license_no
    if id_card:
        payload["id_card"] = id_card
    if law_firm_id is not None:
        payload["law_firm_id"] = law_firm_id
    if lawyer_team_ids is not None:
        payload["lawyer_team_ids"] = lawyer_team_ids
    if biz_team_ids is not None:
        payload["biz_team_ids"] = biz_team_ids
    return client.post("/organization/lawyers", json=payload)  # type: ignore[return-value]


def update_lawyer(
    lawyer_id: int,
    real_name: str | None = None,
    phone: str | None = None,
    license_no: str | None = None,
    id_card: str | None = None,
    law_firm_id: int | None = None,
    is_admin: bool | None = None,
    password: str | None = None,
    lawyer_team_ids: list[int] | None = None,
    biz_team_ids: list[int] | None = None,
) -> dict[str, Any]:
    """更新律师信息。只传需要修改的字段，未传字段不修改。"""
    payload: dict[str, Any] = {}
    if real_name is not None:
        payload["real_name"] = real_name
    if phone is not None:
        payload["phone"] = phone
    if license_no is not None:
        payload["license_no"] = license_no
    if id_card is not None:
        payload["id_card"] = id_card
    if law_firm_id is not None:
        payload["law_firm_id"] = law_firm_id
    if is_admin is not None:
        payload["is_admin"] = is_admin
    if password is not None:
        payload["password"] = password
    if lawyer_team_ids is not None:
        payload["lawyer_team_ids"] = lawyer_team_ids
    if biz_team_ids is not None:
        payload["biz_team_ids"] = biz_team_ids
    return client.put(f"/organization/lawyers/{lawyer_id}", json=payload)  # type: ignore[return-value]


def delete_lawyer(lawyer_id: int) -> None:
    """删除指定律师账号。此操作不可逆。"""
    client.delete(f"/organization/lawyers/{lawyer_id}")
