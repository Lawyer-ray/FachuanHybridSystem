"""Agent UI 上行应答 API —— 前端把「动作结果 / 页面状态」交回正在等待的模型。

端点前缀：``/api/v1/agent``（与提问同域）。请求契约见 ``schemas/ui_schemas.py``，
回执的等待/积压语义见 ``services/ui_action/ack.py``，快照的等待语义见
``services/ui_action/snapshot.py``，审计台账（下发/回执落库 + 历史查询）见
``services/ui_action/audit.py``。

## 为什么返回 ``accepted`` 与 ``success`` 两个布尔

``accepted`` = 这份应答**被系统收下了吗**（契约、鉴权、归属层面成立）；
``success`` = 它**有没有交到正在等待的调用方手里**。前者为真、后者为假是正常结局：
模型只等 2~3 秒，律师慢一步就是超时。此时应答仍应被记录（积压里还能补取），但前端
不该弹成失败——那会让每一次「页面切得慢」都变成一个红条。

## 为什么上行应答本身不落库

提问有 ``AgentQuestion`` 行可以做归属校验，这两条上行应答没有：它们是一次性进程间
消息，TTL 60 秒就消失。归属信息因此由派发方在发出去时写进 Redis
（``request_id → session_id``，与应答同寿命；两条链路共用同一张映射，见
``ack.mark_dispatch_session``），本模块读它再查会话所有者。

M1 之后唯一的数据库落点是**动作审计台账**（``AgentUiAction``）：下发时由
``publish_ui_action`` 写一行，回执到达时本模块推它更新一行。它只记录「谁让 AI 干了
什么、页面回了什么」，不参与归属校验——所以台账写失败也不会把回执变成错误。
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import UiActionResultIn, UiSnapshotIn
from ..services.event_bus import redis_cache_enabled
from ..services.session_service import get_session
from ..services.ui_action import ack, audit, audit_query, snapshot
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
    # 台账就地更新（幂等）：只在那一行还是 ``unknown`` 时才写，重复提交不会覆盖第一份。
    # 放在 ``ack.resolve`` 之后、且不看返回值——回执已经交出去了，台账失败不该改变响应。
    await audit.apply_receipt(
        payload.call_id,
        outcome=payload.outcome,
        code=payload.code,
        location=payload.observed_location,
    )
    return {
        "accepted": True,
        "success": found,
        "note": "" if found else "回执已记录，但等待方已超时（模型已按超时继续，积压里仍可补取）",
    }


@router.get("/ui-actions")
async def list_ui_actions(
    request: Any,
    limit: int = 50,
    action: str = "",
    outcome: str = "",
    risk: str = "",
    decision: str = "",
    since_days: int = 0,
) -> dict[str, Any]:  # pragma: no cover
    """当前用户的 UI 动作审计历史（仅 ``confirm`` / ``guarded`` 档，见 ``audit``）。

    只给**自己的**行：动作历史不是会话共享资产，同一会话被转交后新负责人也不该看见
    前任按过哪些高危按钮。也就因此不经 ``_rejection_reason``：读的不是某个请求的回执。

    ``action`` / ``outcome`` / ``risk`` / ``decision`` 是精确匹配的过滤条件，**空串 =
    不过滤**（默认全给）。为什么是这几个：它们恰好对应事后最常问的几句话——「这个动作我
    批过几次」（action）、「哪些最后没执行成」（outcome 含 ``denied`` / ``expired``）、
    「高危档里我拒过什么」（risk）、「我到底同不同意」（decision = approved / denied /
    expired，与 outcome 是两个主体的问题）。``since_days``（1~90）再叠一道时间窗，
    **0 = 不过滤**（这个参数是后加的，不传等于老行为）。
    过滤在库里做，不在 API 层过滤：后者会先把整页拉进内存再筛，分页一上就是错的。

    Returns:
        ``{"items": [...], "count": n}``；未登录返回空列表 + ``error``（与同文件其余
        端点的「未登录不报 401、给空结果」口径一致）。每项含 ``decision`` / ``decided_at`` /
        ``verified`` / ``verify_note`` / ``batch_id``（字段口径见
        ``audit_query.list_recent_for_user``）。
    """
    user = _current_user(request)
    if user is None:
        return {"items": [], "count": 0, "error": "未登录"}
    items = await audit.list_recent_for_user(
        user,
        limit=limit,
        action=action,
        outcome=outcome,
        risk=risk,
        decision=decision,
        since_days=since_days,
    )
    return {"items": items, "count": len(items)}


@router.get("/ui-actions/stats")
async def ui_action_stats(
    request: Any,
    days: int = audit_query.STATS_WINDOW_DAYS_DEFAULT,
    action: str = "",
) -> dict[str, Any]:  # pragma: no cover
    """当前用户最近 ``days`` 天的动作汇总 —— 「AI 这段时间帮我做了多少事」。

    逐条列表回答不了这个问题（翻 50 行也数不出「成了几个、我拒过几个」），这里只出聚合。
    全部口径（哪些行算进来、``verified_rate`` 的分母、``not_checked`` 与「核实失败」
    为什么分开、``approval_to_dispatch_ms`` **不是**执行耗时、2000 行截断）逐条写在
    ``audit_query.stats_for_user`` 的 docstring 里——那是唯一权威口径，本层只做鉴权与转交。

    ``days`` clamp 到 1~90（``days=0`` / ``days=999`` 都是夹到边界上继续算，不是 500），
    ``action`` 精确匹配、空串 = 不过滤。

    Returns:
        见 ``audit_query.empty_stats`` 的形状；未登录返回全零结构 + ``error``（与同文件
        其余端点的「未登录不报 401、给空结果」口径一致）。
    """
    user = _current_user(request)
    if user is None:
        return {**audit_query.empty_stats(days), "error": "未登录"}
    return await audit_query.stats_for_user(user, days=days, action=action)


@router.post("/ui-snapshots/{request_id}")
async def submit_ui_snapshot(
    request: Any, request_id: str, payload: UiSnapshotIn
) -> dict[str, Any]:  # pragma: no cover
    """前端回传一次页面状态快照（仅会话所有者）。

    契约（脱敏、``state`` 2000 字 / ``private_state`` 4000 字上限）在 ``UiSnapshotIn`` 里；
    本端点只做归属校验与转交。
    ``success=False`` 不是失败：等待方（≤3s）可能已经超时，模型会按「没问到」继续。

    往下转交的六个字段（漏一个就是一条静默失效的通道）：``state`` / ``route`` / ``note`` /
    ``available_actions`` / ``blocked_actions`` / ``private_state``。
    """
    user = _current_user(request)
    if user is None:
        return {"accepted": False, "success": False, "error": "未登录，快照未记录"}

    # 归属映射与动作回执共用一张（``request_snapshot`` 派发时写的就是 ack 的会话键）。
    rejection = await _rejection_reason(user, request_id, what="页面状态快照", window_seconds=ack.ACK_TTL)
    if rejection is not None:
        return {"accepted": False, "success": False, "error": rejection}

    # 这里**逐个关键字**传参是刻意的：新增字段必须在此显式接上，``accept_snapshot`` 的默认值
    # 不是「接上了」——它只是让漏传不抛 TypeError，于是漏传表现为「这条通道永远没有数据」，
    # 既不报错也没有断言会红（``blocked_actions`` 当初就是这么漏的）。端点用例
    # ``test_endpoint_passes_actions_and_private_state_through`` 钉住这几个关键字真的传了下去。
    return await snapshot.accept_snapshot(
        request_id,
        state=payload.state,
        route=payload.route,
        # 页面自己声明的动作名（跨 lane 契约，由 ``UiSnapshotIn`` 提供，默认空列表）。
        # 模型据此知道「这一页现在能调哪些动作」，比让它猜省一轮试错。
        available_actions=payload.available_actions,
        # 与 ``available_actions`` 成对：漏一行就等于这个字段永远拿不到（``accept_snapshot``
        # 的默认值是空表，缺了不报错，只会让模型一直看到「没有什么做不了」）。
        blocked_actions=payload.blocked_actions,
        # 页面的另一半（未提交草稿 / 原始 id / 调试字段）：进日志、**不进**模型上下文。
        private_state=payload.private_state,
    )
