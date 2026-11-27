"""Agent UI 动作回执 API —— 前端把执行结果交回正在等待的模型。

端点前缀：``/api/v1/agent``（与提问同域）。请求契约见 ``schemas/ui_schemas.py``，
回执的等待/积压语义见 ``services/ui_action/ack.py``。

## 为什么返回 ``accepted`` 与 ``success`` 两个布尔

``accepted`` = 这份回执**被系统收下了吗**（契约、鉴权、归属层面成立）；
``success`` = 它**有没有交到正在等待的调用方手里**。前者为真、后者为假是正常结局：
模型只等 2 秒，律师慢一步就是超时。此时回执仍应被记录（积压里还能补取），但前端
不该弹成失败——那会让每一次「页面切得慢」都变成一个红条。

## 为什么这里没有数据库记录

提问有 ``AgentQuestion`` 行可以做归属校验，回执没有：它是一次性进程间消息，
TTL 60 秒就消失。归属信息因此由 ``publish_ui_action`` 在派发时写进 Redis
（``call_id → session_id``，与回执同寿命），本端点读它再查会话所有者。
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import UiActionResultIn
from ..services.event_bus import redis_cache_enabled
from ..services.session_service import get_session
from ..services.ui_action import ack
from ._helpers import _current_user

logger = logging.getLogger(__name__)

router = Router(tags=["Agent UI 动作"], auth=JWTOrSessionAuth())


async def _rejection_reason(user: Any, call_id: str) -> str | None:
    """回执归属校验：返回拒绝理由，``None`` = 放行。

    口径与提问的 ``question_api._may_answer`` 一致——只有会话所有者能替这个会话的
    动作说话（回执会被模型当成事实转述给律师，别人能替你作证就等于没有事实）。

    拿不到归属信息时**不一律拒绝**：没有共享缓存（Redis）时映射本来就写不进去，
    而那种部署下回执也永远到不了等待方（派发在 MCP 进程、回执在 Django 进程），
    伪造它什么也影响不到——所以只留 warning，不把功能整个锁死。
    """
    session_id = ack.dispatch_session(call_id)
    if session_id is None:
        if not redis_cache_enabled():
            logger.warning("无共享缓存，跳过 UI 动作回执的归属校验 call_id=%s user=%s", call_id, user.pk)
            return None
        # 60 秒窗口外或凭空编的 call_id：两者对调用方是同一件事（窗口已经关了）。
        logger.warning("UI 动作回执的 call_id 未知或已过期 call_id=%s user=%s", call_id, user.pk)
        return "call_id 未知或已过期（回执窗口 60 秒）"
    session = await get_session(session_id=session_id, user_id=int(user.pk))
    if session is None:
        logger.warning(
            "UI 动作回执归属校验失败 call_id=%s session=%s user=%s",
            call_id,
            session_id,
            user.pk,
        )
        return "无权提交该动作结果"
    return None


@router.post("/ui-action-results")
async def submit_ui_action_result(request: Any, payload: UiActionResultIn) -> dict[str, Any]:  # pragma: no cover
    """前端提交一次 UI 动作的执行结果（仅会话所有者）。

    ``success=False`` 不一定是错误：等待方可能已经超时（模型只等 2 秒）。前端应提示
    「结果已记录，但本轮已按超时继续」，而不是当成失败重试——重试也只会命中
    :func:`ack.resolve` 的幂等分支（第二次提交不生效）。
    """
    user = _current_user(request)
    if user is None:
        return {"accepted": False, "success": False, "error": "未登录，回执未记录"}

    rejection = await _rejection_reason(user, payload.call_id)
    if rejection is not None:
        return {"accepted": False, "success": False, "error": rejection}

    # 字段名换成模型侧的口径（``observed_location`` → ``location``）：回执迟早会被
    # 拼进工具返回值，在边界上换一次名，比让模型读两套拼法便宜。
    found = await ack.resolve(
        payload.call_id,
        {
            "outcome": payload.outcome,
            "code": payload.code,
            "detail": payload.detail,
            "location": payload.observed_location,
        },
    )
    return {
        "accepted": True,
        "success": found,
        "note": "" if found else "回执已记录，但等待方已超时（模型已按超时继续，积压里仍可补取）",
    }
