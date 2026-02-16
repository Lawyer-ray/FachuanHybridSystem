"""
团队 API
负责请求/响应处理，所有业务逻辑委托给 TeamService
"""
from typing import List, Optional
from ninja import Router
from ..schemas import TeamOut, TeamIn

router = Router()


def _get_team_service():
    """工厂函数：创建 TeamService 实例"""
    from ..services import TeamService
    return TeamService()


@router.get("/teams", response=List[TeamOut])
def list_teams(
    request,
    law_firm_id: Optional[int] = None,
    team_type: Optional[str] = None
):
    """列表查询团队"""
    service = _get_team_service()
    user = getattr(request, "user", None)
    return service.list_teams(
        law_firm_id=law_firm_id,
        team_type=team_type,
        user=user
    )


@router.post("/teams", response=TeamOut)
def create_team(request, payload: TeamIn):
    """创建团队"""
    service = _get_team_service()
    user = getattr(request, "user", None)
    return service.create_team(data=payload, user=user)


@router.get("/teams/{team_id}", response=TeamOut)
def get_team(request, team_id: int):
    """获取团队详情"""
    service = _get_team_service()
    user = getattr(request, "user", None)
    return service.get_team(team_id=team_id, user=user)


@router.put("/teams/{team_id}", response=TeamOut)
def update_team(request, team_id: int, payload: TeamIn):
    """更新团队"""
    service = _get_team_service()
    user = getattr(request, "user", None)
    return service.update_team(team_id=team_id, data=payload, user=user)


@router.delete("/teams/{team_id}")
def delete_team(request, team_id: int):
    """删除团队"""
    service = _get_team_service()
    user = getattr(request, "user", None)
    service.delete_team(team_id=team_id, user=user)
    return {"success": True}
