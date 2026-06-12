"""案件访问权限 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_grants(case_id: int) -> list[dict[str, Any]]:
    """查询案件的访问权限列表。"""
    return client.get("/cases/grants", params={"case_id": case_id})  # type: ignore[return-value]


def create_grant(case_id: int, lawyer_id: int, permission_level: str = "read") -> dict[str, Any]:
    """为案件添加访问权限。permission_level: read / write / admin。"""
    return client.post(  # type: ignore[return-value]
        "/cases/grants",
        json={"case_id": case_id, "lawyer_id": lawyer_id, "permission_level": permission_level},
    )


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
