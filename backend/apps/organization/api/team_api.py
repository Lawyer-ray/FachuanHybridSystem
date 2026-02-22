"""
团队 API
负责请求/响应处理，所有业务逻辑委托给 TeamService
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.organization.dtos import TeamUpsertDTO
from apps.organization.schemas import TeamIn, TeamOut
from apps.organization.services import TeamService

router = Router()


def _get_team_service() -> TeamService:
    """工厂函数：创建 TeamService 实例"""
    return TeamService()


@router.get("/teams", response=list[TeamOut])
def list_teams(request: HttpRequest, law_firm_id: int | None = None, team_type: str | None = None) -> list[TeamOut]:
    """列表查询团队"""
    service = _get_team_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.list_teams(law_firm_id=law_firm_id, team_type=team_type, user=user)


@router.post("/teams", response=TeamOut)
def create_team(request: HttpRequest, payload: TeamIn) -> TeamOut:
    """创建团队"""
    service = _get_team_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    dto = TeamUpsertDTO(name=payload.name, team_type=payload.team_type, law_firm_id=payload.law_firm_id)
    return service.create_team(data=dto, user=user)


@router.get("/teams/{team_id}", response=TeamOut)
def get_team(request: HttpRequest, team_id: int) -> TeamOut:
    """获取团队详情"""
    service = _get_team_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.get_team(team_id=team_id, user=user)


@router.put("/teams/{team_id}", response=TeamOut)
def update_team(request: HttpRequest, team_id: int, payload: TeamIn) -> TeamOut:
    """更新团队"""
    service = _get_team_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    dto = TeamUpsertDTO(name=payload.name, team_type=payload.team_type, law_firm_id=payload.law_firm_id)
    return service.update_team(team_id=team_id, data=dto, user=user)


@router.delete("/teams/{team_id}")
def delete_team(request: HttpRequest, team_id: int) -> dict[str, bool]:
    """删除团队"""
    service = _get_team_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    service.delete_team(team_id=team_id, user=user)
    return {"success": True}
