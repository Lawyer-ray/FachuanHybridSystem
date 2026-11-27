"""Agent UI 上行应答 API —— 前端把「动作结果 / 页面状态」交回正在等待的模型。

端点前缀：``/api/v1/agent``（与提问同域）。请求契约见 ``schemas/ui_schemas.py``，
回执的等待/积压语义见 ``services/ui_action/ack.py``，快照的等待语义见
``services/ui_action/snapshot.py``。

## 为什么返回 ``accepted`` 与 ``success`` 两个布尔

``accepted`` = 这份应答**被系统收下了吗**（契约、鉴权、归属层面成立）；
``success`` = 它**有没有交到正在等待的调用方手里**。前者为真、后者为假是正常结局：
模型只等 2~3 秒，律师慢一步就是超时。此时应答仍应被记录（积压里还能补取），但前端
不该弹成失败——那会让每一次「页面切得慢」都变成一个红条。

## 为什么这里没有数据库记录

提问有 ``AgentQuestion`` 行可以做归属校验，这两条上行应答没有：它们是一次性进程间
消息，TTL 60 秒就消失。归属信息因此由派发方在发出去时写进 Redis
（``request_id → session_id``，与应答同寿命；两条链路共用同一张映射，见
``ack.mark_dispatch_session``），本模块读它再查会话所有者。
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import UiActionResultIn, UiSnapshotIn
from ..services.event_bus import redis_cache_enabled
from ..services.session_service import get_session
from ..services.ui_action import ack, snapshot
from ._helpers import _current_user

logger = logging.getLogger(__name__)

router = Router(tags=["Agent UI 动作"], auth=JWTOrSessionAuth())


async def _rejection_reason(user: Any, request_id: str, *, what: str, window_seconds: int) -> str | None:
    """上行应答的归属校验：返回拒绝理由，``None`` = 放行。

    口径与提问的 ``question_api._may_answer`` 一致——只有会话所有者能替这个会话的
    请求说话（应答会被模型当成事实转述给律师，别人能替你作证就等于没有事实）。

    拿不到归属信息时**不一律拒绝**：没有共享缓存（Redis）时映射本来就写不进去，
    而那种部署下应答也永远到不了等待方（派发在 MCP 进程、应答在 Django 进程），
    伪造它什么也影响不到——所以只留 warning，不把功能整个锁死。
    """
    session_id = ack.dispatch_session(request_id)
    if session_id is None:
        if not redis_cache_enabled():
            logger.warning("无共享缓存，跳过%s的归属校验 request_id=%s user=%s", what, request_id, user.pk)
            return None
        # 窗口外或凭空编的 request_id：两者对调用方是同一件事（窗口已经关了）。
        logger.warning("%s的 request_id 未知或已过期 request_id=%s user=%s", what, request_id, user.pk)
        return f"请求 id 未知或已过期（{window_seconds} 秒窗口）"
    session = await get_session(session_id=session_id, user_id=int(user.pk))
    if session is None:
        logger.warning("%s归属校验失败 request_id=%s session=%s user=%s", what, request_id, session_id, user.pk)
        return f"无权提交这份{what}"
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

    rejection = await _rejection_reason(user, payload.call_id, what="动作回执", window_seconds=ack.ACK_TTL)
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


@router.post("/ui-snapshots/{request_id}")
async def submit_ui_snapshot(
    request: Any, request_id: str, payload: UiSnapshotIn
) -> dict[str, Any]:  # pragma: no cover
    """前端回传一次页面状态快照（仅会话所有者）。

    契约（脱敏、2000 字上限）在 ``UiSnapshotIn`` 里；本端点只做归属校验与转交。
    ``success=False`` 不是失败：等待方（≤3s）可能已经超时，模型会按「没问到」继续。
    """
    user = _current_user(request)
    if user is None:
        return {"accepted": False, "success": False, "error": "未登录，快照未记录"}

    # 归属映射与动作回执共用一张（``request_snapshot`` 派发时写的就是 ack 的会话键）。
    rejection = await _rejection_reason(user, request_id, what="页面状态快照", window_seconds=ack.ACK_TTL)
    if rejection is not None:
        return {"accepted": False, "success": False, "error": rejection}

    return await snapshot.accept_snapshot(request_id, state=payload.state, route=payload.route)
