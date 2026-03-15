"""
团队 API
负责请求/响应处理，所有业务逻辑委托给 TeamService
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.core.auth import JWTOrSessionAuth
from apps.organization.api._utils import get_request_user
from apps.organization.dtos import TeamUpsertDTO
from apps.organization.schemas import TeamIn, TeamOut
from apps.organization.services import TeamService

router = Router(auth=JWTOrSessionAuth())


def _get_team_service() -> TeamService:
    """工厂函数：获取团队服务实例"""
    return TeamService()


_team_service = _get_team_service()


@router.get("/teams", response=list[TeamOut])
def list_teams(request: HttpRequest, law_firm_id: int | None = None, team_type: str | None = None) -> list[TeamOut]:
    return list(_team_service.list_teams(law_firm_id=law_firm_id, team_type=team_type, user=get_request_user(request)))


@router.post("/teams", response=TeamOut)
def create_team(request: HttpRequest, payload: TeamIn) -> TeamOut:
    dto = TeamUpsertDTO(name=payload.name, team_type=payload.team_type, law_firm_id=payload.law_firm_id)
    return _team_service.create_team(data=dto, user=get_request_user(request))


@router.get("/teams/{team_id}", response=TeamOut)
def get_team(request: HttpRequest, team_id: int) -> TeamOut:
    return _team_service.get_team(team_id=team_id, user=get_request_user(request))


@router.put("/teams/{team_id}", response=TeamOut)
def update_team(request: HttpRequest, team_id: int, payload: TeamIn) -> TeamOut:
    dto = TeamUpsertDTO(name=payload.name, team_type=payload.team_type, law_firm_id=payload.law_firm_id)
    return _team_service.update_team(team_id=team_id, data=dto, user=get_request_user(request))


@router.delete("/teams/{team_id}")
def delete_team(request: HttpRequest, team_id: int) -> dict[str, bool]:
    _team_service.delete_team(team_id=team_id, user=get_request_user(request))
    return {"success": True}
