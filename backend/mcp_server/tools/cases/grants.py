"""案件访问权限 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_grants(case_id: int) -> list[dict[str, Any]]:
    """查询案件的访问权限列表。"""
    return client.get("/cases/grants", params={"case_id": case_id})  # type: ignore[return-value]


def create_grant(case_id: int, grantee_id: int) -> dict[str, Any]:
    """为指定律师授予案件访问权限。

    后端 ``CaseAccessGrantIn`` 只有 ``case_id`` + ``grantee_id`` 两个字段：
    早前签名用 ``lawyer_id`` 且额外传 ``permission_level``，字段名与结构都不符，
    调用必然 422。授权粒度就是「可见/不可见」，没有读写分级。

    Args:
        case_id: 案件 ID。
        grantee_id: 被授权律师的 ID（Lawyer 主键）。
    """
    return client.post("/cases/grants", json={"case_id": case_id, "grantee_id": grantee_id})  # type: ignore[no-any-return]


def get_grant(grant_id: int) -> dict[str, Any]:
    """获取单条案件访问权限详情。"""
    return client.get(f"/cases/grants/{grant_id}")  # type: ignore[return-value]


def update_grant(grant_id: int, permission_level: str | None = None) -> dict[str, Any]:
    """更新案件访问权限。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if permission_level is not None:
        payload["permission_level"] = permission_level
    return client.put(f"/cases/grants/{grant_id}", json=payload)  # type: ignore[return-value]


def delete_grant(grant_id: int) -> None:
    """删除案件访问权限。"""
    client.delete(f"/cases/grants/{grant_id}")
