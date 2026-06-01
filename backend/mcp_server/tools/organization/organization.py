"""组织架构 MCP tools（律师、团队）"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_lawyers(team_id: int | None = None) -> list[dict[str, Any]]:
    """查询律师列表。可按团队（team_id）筛选。返回律师 ID、姓名、团队等信息，用于指派律师时选择。"""
    params: dict[str, Any] = {}
    if team_id is not None:
        params["team_id"] = team_id
    return client.get("/organization/lawyers", params=params)  # type: ignore[return-value]


def list_teams() -> list[dict[str, Any]]:
    """查询所有团队列表。"""
    return client.get("/organization/teams")  # type: ignore[return-value]
