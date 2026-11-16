"""Agent 技能 API —— `/` 命令菜单数据源与启停。

端点前缀：``/api/v1/agent``（技能子域）。消息以 ``/skill:名字 参数`` 触发，
pi 在发给模型前展开全文。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import SkillListOut, SkillOut, SkillToggleIn, SkillToggleOut
from ..services import skill_service
from ._helpers import _user_id

router = Router(tags=["Agent 技能"], auth=JWTOrSessionAuth())


@router.get("/skills", response=SkillListOut)
async def list_skills(request: Any) -> SkillListOut:  # pragma: no cover
    """当前律师可见的技能清单（偏好只记差异，缺省全启用）。"""
    skills = await sync_to_async(skill_service.skills_for_user, thread_sensitive=True)(_user_id(request) or 0)
    return SkillListOut(skills=[SkillOut(**item) for item in skills])


@router.patch("/skills/{skill_name}", response=SkillToggleOut)
async def toggle_skill(request: Any, skill_name: str, payload: SkillToggleIn) -> SkillToggleOut:  # pragma: no cover
    """启停一个技能（下一轮对话生效：注入面按用户偏好逐个 ``--skill``）。"""
    try:
        result = await sync_to_async(skill_service.set_skill_enabled, thread_sensitive=True)(
            _user_id(request) or 0, skill_name, payload.enabled
        )
    except ValueError as exc:
        raise HttpError(404, str(exc)) from exc
    return SkillToggleOut(name=str(result["name"]), enabled=bool(result["enabled"]))
