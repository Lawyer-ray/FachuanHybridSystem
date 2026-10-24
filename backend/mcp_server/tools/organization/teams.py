"""团队管理 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_teams(
    law_firm_id: int | None = None,
    team_type: str | None = None,
) -> dict[str, Any]:
    """查询团队列表。可按律所（law_firm_id）和团队类型（team_type，如 lawyer/biz）筛选。"""
    params: dict[str, Any] = {}
    if law_firm_id is not None:
        params["law_firm_id"] = law_firm_id
    if team_type:
        params["team_type"] = team_type
    return list_result(client.get("/organization/teams", params=params))


def get_team(team_id: int) -> dict[str, Any]:
    """获取单个团队详情（成员、负责人）。"""
    return client.get(f"/organization/teams/{team_id}")  # type: ignore[no-any-return]


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
    return client.post("/organization/teams", json=payload)  # type: ignore[no-any-return]


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
    return client.put(f"/organization/teams/{team_id}", json=payload)  # type: ignore[no-any-return]


def delete_team(team_id: int) -> None:
    """删除团队——管理员操作;只删团队,成员律师账号不受影响。"""
    client.delete(f"/organization/teams/{team_id}")
