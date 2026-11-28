"""Agent 技能 API —— 个人技能增删改查 + 启停 + 校验 + 复制内置。

端点前缀：``/api/v1/agent``（技能子域）。消息以 ``/skill:名字 参数`` 触发，
pi 在发给模型前展开全文。

## 两条实现纪律

1. **路由顺序**：``/skills/quota``、``/skills/validate`` 必须注册在
   ``/skills/{key}`` 之前，否则会被路径参数吞掉。
2. **API 层零 ORM**（四层棘轮）：所有查询/校验/写盘在 ``services/skills/``；
   这里只做参数装配与把领域异常翻译成 HTTP 状态码。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router, Status
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import (
    SkillCreateIn,
    SkillDetailOut,
    SkillFieldError,
    SkillListOut,
    SkillOut,
    SkillQuotaOut,
    SkillToggleIn,
    SkillToggleOut,
    SkillUpdateIn,
    SkillValidateIn,
    SkillValidateOut,
)
from ..services import skill_service
from ..services.skills import errors as skill_errors
from ..services.skills import user_skills
from ._helpers import _user_id

router = Router(tags=["Agent 技能"], auth=JWTOrSessionAuth())


async def _invoke(func: Any, **kwargs: Any) -> Any:
    """在线程里跑同步 service，并把领域错误翻译成 ``HttpError``。

    ``ValueError`` 是 ``skill_service.set_skill_enabled`` 的兼容行为（改造前就用
    它表示「非法/未知技能名」），对前端都是 404。
    """
    try:
        return await sync_to_async(func, thread_sensitive=True)(**kwargs)
    except skill_errors.SkillNotFound as exc:
        raise HttpError(404, str(exc)) from exc
    except skill_errors.SkillForbidden as exc:
        raise HttpError(403, str(exc)) from exc
    except skill_errors.SkillConflict as exc:
        raise HttpError(409, str(exc)) from exc
    except skill_errors.SkillQuotaExceeded as exc:
        raise HttpError(429, str(exc)) from exc
    except skill_errors.SkillInvalid as exc:
        raise HttpError(422, skill_errors.as_message(exc.errors)) from exc
    except ValueError as exc:
        raise HttpError(404, str(exc)) from exc


@router.get("/skills", response=SkillListOut)
async def list_skills(request: Any) -> SkillListOut:
    """当前律师可见的技能清单（内置 + 个人，含禁用项）。"""
    skills = await _invoke(user_skills.list_for_user, user_id=_user_id(request) or 0)
    return SkillListOut(skills=[SkillOut(**item) for item in skills])


@router.get("/skills/quota", response=SkillQuotaOut)
async def skill_quota(request: Any) -> SkillQuotaOut:
    """个人技能配额（前端进度条）。"""
    quota = await _invoke(user_skills.quota_for_user, user_id=_user_id(request) or 0)
    return SkillQuotaOut(**quota)


@router.post("/skills/validate", response=SkillValidateOut)
async def validate_skill(request: Any, payload: SkillValidateIn) -> SkillValidateOut:
    """字段级校验 + 渲染预览（不落库）。"""
    result = await _invoke(
        user_skills.validate_form,
        user_id=_user_id(request) or 0,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        body=payload.body,
    )
    return SkillValidateOut(
        ok=bool(result["ok"]),
        errors=[SkillFieldError(**error) for error in result["errors"]],
        preview=str(result["preview"]),
    )


@router.get("/skills/{key}", response=SkillDetailOut)
async def get_skill(request: Any, key: str) -> SkillDetailOut:
    """技能详情（含正文）。``key`` 可含 ``:``（``builtin:web-research``）。"""
    detail = await _invoke(user_skills.get_detail, user_id=_user_id(request) or 0, key=key)
    return SkillDetailOut(**detail)


@router.post("/skills", response={201: SkillDetailOut})
async def create_skill(request: Any, payload: SkillCreateIn) -> Any:
    """新建个人技能；``name`` 省略时后端生成。"""
    detail = await _invoke(
        user_skills.create_skill,
        user_id=_user_id(request) or 0,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        body=payload.body,
    )
    return Status(201, SkillDetailOut(**detail))


@router.put("/skills/{key}", response=SkillDetailOut)
async def update_skill(request: Any, key: str, payload: SkillUpdateIn) -> SkillDetailOut:
    """更新正文与描述；``version`` 不符返回 409。"""
    detail = await _invoke(
        user_skills.update_skill,
        user_id=_user_id(request) or 0,
        key=key,
        title=payload.title,
        description=payload.description,
        body=payload.body,
        expected_version=payload.version,
    )
    return SkillDetailOut(**detail)


@router.patch("/skills/{key}", response=SkillToggleOut)
async def toggle_skill(request: Any, key: str, payload: SkillToggleIn) -> SkillToggleOut:
    """启停（下一轮对话生效：注入面按用户偏好逐个 ``--skill``）。"""
    result = await _invoke(
        skill_service.set_skill_enabled,
        user_id=_user_id(request) or 0,
        key=key,
        enabled=payload.enabled,
    )
    return SkillToggleOut(key=str(result["key"]), enabled=bool(result["enabled"]))


@router.delete("/skills/{key}", response={204: None})
async def delete_skill(request: Any, key: str) -> Any:
    """删除个人技能（内置技能 403）。"""
    await _invoke(user_skills.delete_skill, user_id=_user_id(request) or 0, key=key)
    return Status(204, None)


@router.post("/skills/{key}/duplicate", response={201: SkillDetailOut})
async def duplicate_skill(request: Any, key: str) -> Any:
    """「复制为我的」：仅内置技能可复制。"""
    detail = await _invoke(user_skills.duplicate_builtin, user_id=_user_id(request) or 0, key=key)
    return Status(201, SkillDetailOut(**detail))
