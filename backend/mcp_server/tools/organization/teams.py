"""团队管理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_teams(
    law_firm_id: int | None = None,
    team_type: str | None = None,
) -> list[dict[str, Any]]:
    """查询团队列表。可按律所（law_firm_id）和团队类型（team_type，如 lawyer/biz）筛选。"""
    params: dict[str, Any] = {}
    if law_firm_id is not None:
        params["law_firm_id"] = law_firm_id
    if team_type:
        params["team_type"] = team_type
    return client.get("/organization/teams", params=params)  # type: ignore[return-value]


def get_team(team_id: int) -> dict[str, Any]:
    """获取单个团队的详细信息。"""
    return client.get(f"/organization/teams/{team_id}")  # type: ignore[return-value]


def create_team(
    name: str,
    team_type: str,
    law_firm_id: int,
) -> dict[str, Any]:
    """创建新团队。team_type 为 lawyer（律师团队）或 biz（业务团队）；law_firm_id 关联所属律所。"""
    payload: dict[str, Any] = {
        "name": name,
        "team_type": team_type,
        "law_firm_id": law_firm_id,
    }
    return client.post("/organization/teams", json=payload)  # type: ignore[return-value]


def update_team(
    team_id: int,
    name: str,
    team_type: str,
    law_firm_id: int,
) -> dict[str, Any]:
    """更新团队信息。name、team_type、law_firm_id 均为必填。"""
    payload: dict[str, Any] = {
        "name": name,
        "team_type": team_type,
        "law_firm_id": law_firm_id,
    }
    return client.put(f"/organization/teams/{team_id}", json=payload)  # type: ignore[return-value]


def delete_team(team_id: int) -> None:
    """删除指定团队。此操作不可逆。"""
    client.delete(f"/organization/teams/{team_id}")
