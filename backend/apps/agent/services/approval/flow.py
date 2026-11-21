"""审批主流程 —— 发起审批、阻塞等待、提交决定（fail-closed）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone

from ...models import AgentApproval, AgentSession
from ..event_bus import redis_cache_enabled
from .policy import lookup_approval_policy, multi_lane_write_refusal
from .risk import (
    OFFLINE_TIMEOUT,
    RiskLevel,
    approval_timeout,
    classify_risk,
    needs_second_confirmation,
    short_tool_name,
)
from .waiter import (
    _clear_decision,
    _clear_waiter_heartbeat,
    _wait_decision,
    _waiter,
    _write_decision,
    _write_waiter_heartbeat,
)

logger = logging.getLogger(__name__)

#: 离线审批开关（``FACHUAN_APPROVAL_OFFLINE=0`` 可关闭，回到纯 fail-closed）。
OFFLINE_ENV = "FACHUAN_APPROVAL_OFFLINE"

#: 「超时后补批」的放行有效期（秒）。与 MCP 闸门的 Redis 台账 TTL 同量级：
#: 批了之后模型要在这么久之内原样重试一次，否则重新走一遍审批。
LATE_GRANT_SECONDS = 600


def allow_offline_approval() -> bool:
    """无人在线时是否允许挂起等离线审批。

    默认**允许**：否则任务式入口（后台跑）永远用不了任何高危工具——
    这条路是无 SSE 连接的，fail-closed 直接把它判死。

    关闭后回到「无人可问即拒绝」，适合对安全性要求极端保守的部署。
    """
    import os

    raw = os.environ.get(OFFLINE_ENV, "").strip()
    if not raw:
        return True
    return raw not in ("0", "false", "False", "no")


@asynccontextmanager
async def _sse_channel(
    session_id: str | None,
) -> AsyncIterator[asyncio.Queue[dict[str, Any]] | None]:
    """登记 SSE 通道；无会话上下文时给出 ``None``（调用方按拒绝处理）。"""
    from ..event_bus import get_bus

    if not session_id:
        yield None
        return
    queue = await get_bus().register(session_id)
    try:
        yield queue
    finally:
        await get_bus().unregister(session_id, queue)


async def _has_remote_subscribers(bus: Any, session_id: str) -> bool:
    """本进程之外是否还有人订阅（Redis 计数）。

    用 ``getattr`` 兜底是为了假总线（测试里的 ``_Bus`` 只实现
    ``has_subscribers`` / ``publish``）不至于因为多了个方法就要全改一遍；
    真总线一定有这个方法（``EventBus.remote_subscriber_count``）。
    """
    counter = getattr(bus, "remote_subscriber_count", None)
    if counter is None:
        return False
    with suppress(Exception):
        return int(await counter(session_id) or 0) > 0
    return False


def approval_dedupe_key(*, session_id: str | None, tool_name: str, tool_args: dict[str, Any] | None) -> str:
    """同一调用的去重键：``sha256(session|短工具名|稳定参数)``。

    三个入口（pi 扩展���MCP 服务端闸门、写端点兑底）共用同一张审批卡，
    必须以「会话 + 工具 + 参数」为键；只用工具名会把「删 A 案」与
    「删 B 案」合成一张卡。
    """
    payload = json.dumps(
        {
            "s": session_id or "",
            "t": short_tool_name(tool_name),
            "a": tool_args or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _approval_message(tool_name: str, level: RiskLevel) -> str:
    """给前端弹窗用的提示语（按等级区分措辞，避免一律「高风险」而失去区分度）。"""
    short = short_tool_name(tool_name)
    if level == RiskLevel.CRITICAL:
        return f"即将执行批量破坏性操作：{short}。这会影响多条数据且不可撤回，请再次确认。"
    return f"即将执行不可撤回操作：{short}，请确认是否继续。"


async def _await_and_finalize(
    record: AgentApproval,
    approval_id: str,
    event: asyncio.Event,
    timeout: float,
    *,
    tool_name: str,
    timeout_message: str,
) -> tuple[bool, str, str]:
    """阻塞等待决定并落库收尾（在线 / 离线两条等待路径共用）。

    超时按拒绝处理（fail-closed）；无论结果如何都清理等待者与 Redis 键，
    并把最终状态落库。``timeout_message`` 是超时日志的格式串（两条路径
    措辞不同，逐字保留）。
    """
    try:
        approved = await _wait_decision(approval_id, event, timeout)
        record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
    except TimeoutError:
        record.status = AgentApproval.Status.TIMEOUT
        logger.info(timeout_message, tool_name, approval_id)
    finally:
        await _waiter.discard(approval_id)
        _clear_waiter_heartbeat(approval_id)
        _clear_decision(approval_id)
        # 取消路径（客户端断开 / 进程收尾）会带着 PENDING 进来：显式置 cancelled。
        # 不置的话这条记录要等 7200s 的僵尸清理才变，前端一直显示「待审批」。
        if record.status == AgentApproval.Status.PENDING:
            record.status = AgentApproval.Status.CANCELLED
        record.decided_at = timezone.now()
        # 落库用 shield：本函数常在**已被取消**的任务里跑，裸 await 会再抛
        # CancelledError，把状态改回 PENDING（实测会留下僵尸行）。
        with suppress(Exception):
            await asyncio.shield(record.asave(update_fields=["status", "decided_at"]))
    # 驳回理由由**另一个 ORM 实例**写入（decide_approval），必须回读；
    # 不回读时模型永远收到「用户拒绝或超时」那句兜底文案，驳回意见就断了。
    with suppress(Exception):
        await record.arefresh_from_db(fields=["status", "reason", "decision_reason"])
    granted = record.is_granted
    reason_out = record.decision_reason or record.reason or ("用户同意" if granted else "用户拒绝或超时")
    return granted, approval_id, reason_out


async def request_approval(
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    reason: str = "",
    run_id: str = "",
    tool_call_id: str = "",
    timeout: float | None = None,
    offline_timeout: float = OFFLINE_TIMEOUT,
) -> tuple[bool, str, str]:
    """发起一次审批并阻塞等待。

    分级判定取代原来的布尔判定：中级（常规写）静默放行但记审计标记，
    紧急级（批量清空）要求前端二次确认并给更长的等待时间。

    Args:
        timeout: 显式指定等待上限；``None`` 时按风险等级取（紧急级更长）。
        offline_timeout: 无人在线时挂起等离线决定的上限。

    Returns:
        ``(approved, approval_id)``。``approved`` 为 ``True`` 才放行。
    """
    approval_id = uuid.uuid4().hex

    # 多栏并答时写类工具**直接拒绝**，不弹审批卡：三栏同时改同一份文件是结构性
    # 冲突，让人去批准它没有意义（批准了也必然互相覆盖）。放在分级与用户策略
    # 之前——`allow` 策略同样不许给这条路开绿灯。
    refusal = multi_lane_write_refusal(session_id=session_id, tool_name=tool_name)
    if refusal is not None:
        logger.info("多栏并答拒绝写类工具（不弹审批卡）tool=%s session=%s", tool_name, session_id)
        return False, "", refusal

    level = classify_risk(tool_name, tool_args)
    if level in (RiskLevel.LOW, RiskLevel.MEDIUM):
        # 中级放行但要留痕：出事时能查到「agent 自己改过金额」
        if level == RiskLevel.MEDIUM:
            logger.info(
                "中级风险工具静默执行 tool=%s args=%s",
                tool_name,
                sorted((tool_args or {}).keys()),
            )
        return True, approval_id, "低/中风险，免审批放行"

    # ── P2-5 审批策略覆盖（用户偏好层）──
    # critical 不可被 allow 覆盖（硬红线）；high 可被 allow/deny 覆盖；
    # medium 可被 deny 覆盖（更严）；low 本来就不审批
    policy = await sync_to_async(
        lambda: lookup_approval_policy(user_id=user_id, tool_name=tool_name),
        thread_sensitive=True,
    )()
    if policy == "allow" and level == RiskLevel.HIGH:
        logger.info("策略允许（high→allow）tool=%s user=%s", tool_name, user_id)
        return True, "", "策略允许（用户配置 high 级免审批）"
    if policy == "deny" and level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
        logger.info("策略拒绝 tool=%s user=%s", tool_name, user_id)
        return False, "", f"策略拒绝（用户配置 {level.value} 级禁止）"

    effective_timeout = timeout if timeout is not None else approval_timeout(level)

    # ── 三入口去重 ──
    # 同一 (会话, 工具, 参数) 已在等待时，第二个入口直接返回「正在等待」：
    # 不新建记录、也不弹第二张卡——否则一次删除会弹两张、等两次。
    dedupe_key = approval_dedupe_key(session_id=session_id, tool_name=tool_name, tool_args=tool_args)
    pending = (
        await AgentApproval.objects.filter(dedupe_key=dedupe_key, status=AgentApproval.Status.PENDING)
        .exclude(approval_id=uuid.UUID(approval_id))
        .order_by("-created_at")
        .afirst()
    )
    if pending is not None and (pending.expires_at is None or pending.expires_at > timezone.now()):
        logger.info(
            "同一调用已在等待审批，复用既有审批单 tool=%s approval=%s",
            tool_name,
            pending.approval_id,
        )
        return (
            False,
            pending.approval_id.hex,
            "同一调用已在等待审批，不要重复发起：等律师确认后原样重试一次即可",
        )

    session = None
    if session_id:
        try:
            session = await AgentSession.objects.filter(session_id=session_id).afirst()
        except Exception:
            # 审批记录将丢失会话关联(审计断链),不是可无感降级的失败。
            logger.warning("按 session_id 查会话失败(审批记录将缺会话关联): %s", session_id, exc_info=True)

    record = await AgentApproval.objects.acreate(
        approval_id=uuid.UUID(approval_id),
        session=session,
        tool_name=tool_name,
        tool_args=tool_args or {},
        reason=reason,
        risk_level=level.value,
        run_id=(run_id or "")[:64],
        tool_call_id=(tool_call_id or "")[:120],
        dedupe_key=dedupe_key,
        # 上限取两条等待路径里更长的那个：在线/离线分支在下面才定，
        # 这里先封锁一个宽限期，收尾时不会再有别的写入点。
        expires_at=timezone.now() + timedelta(seconds=max(effective_timeout, offline_timeout)),
    )

    # 先登记等待者、再 publish。反过来的话，若「用户决定」先于 register 到达
    # （自动审批 / 前端重试），resolve 找不到等待者只能落库 approved，等待方
    # 却等不到事件，最终超时分支会把已 approved 的记录覆盖成 timeout——
    # 用户点了同意、工具却被拒。
    delivered = 0
    has_remote = False
    event: asyncio.Event | None = None
    if session_id:
        event = await _waiter.register(approval_id)
        # P2-4 waiter 心跳：Redis 键带 TTL，键过期 = 等待进程已死
        _write_waiter_heartbeat(approval_id, effective_timeout)
        from ..event_bus import get_bus

        bus = get_bus()
        # 订阅者可能在**别的 worker**（SSE 连接在 A，审批回调落在 B）。
        # 多 worker 下 publish 到 Redis 即可送达，此时本地 delivered 为 0
        # 但仍有远端订阅者，不能据此判为「无人可问」。
        # 真实「有没有人在看」= 本进程订阅者 + 其他 worker 的订阅者（Redis 计数）。
        # 不能再用 ``redis_cache_enabled()`` 代替：生产用的就是 Redis，那会让
        # has_remote 恒为 True，离线挂起分支永远不可达（审批只剩 300/900s）。
        # 没有 Redis 就不可能有「别的 worker 上的订阅者」，没必要也不应该去查。
        has_remote = await bus.has_subscribers(session_id) or (
            redis_cache_enabled() and await _has_remote_subscribers(bus, session_id)
        )
        run_parts = (run_id or "").split(":")
        agent_kind = run_parts[-2] if len(run_parts) >= 3 else ""
        delivered = await bus.publish(
            session_id,
            {
                "type": "approval_request",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "tool_args": tool_args or {},
                "risk_level": level.value,
                "needs_second_confirmation": needs_second_confirmation(level),
                "message": reason or _approval_message(tool_name, level),
                # _RunScoped 契约要求每帧带 run_id/agent：三栏并答时前端
                # 靠这两个字段把审批卡挂到正确的那一栏。
                "run_id": run_id or "",
                "agent": agent_kind,
            },
        )

    if event is not None and (delivered or has_remote):
        return await _await_and_finalize(
            record,
            approval_id,
            event,
            effective_timeout,
            tool_name=tool_name,
            timeout_message="审批超时，按拒绝处理: tool=%s approval=%s",
        )

    # 没有订阅者：无人可问。
    #
    # 原实现直接 rejected（fail-closed）。对「用户开着页面但断线」是对的，
    # 但它把「任务式后台运行」这条路彻底堵死了——后台跑本来就没有 SSE 连接，
    # 那意味着任务式入口永远用不了任何高危工具。
    #
    # 现在按「有没有人在线」分流：
    # - 有人在别的 worker 上连着（has_remote）却还是没送达 → 链路异常，仍拒绝；
    # - 完全没人在线且允许离线审批 → 保持 pending 挂起，等用户回来在会话里
    #   看到待审批卡片再决定（离线审批）。工具调用方仍在阻塞等待，
    #   所以等待上限用 offline_timeout。
    # - 完全没人在线且不允许离线审批 → 维持原 fail-closed 行为。
    offline_ok = allow_offline_approval() and not has_remote
    if event is not None and offline_ok:
        logger.info(
            "无人订阅，审批挂起等待离线决定 tool=%s approval=%s timeout=%s",
            tool_name,
            approval_id,
            offline_timeout,
        )
        return await _await_and_finalize(
            record,
            approval_id,
            event,
            offline_timeout,
            tool_name=tool_name,
            timeout_message="离线审批超时，按拒绝处理 tool=%s approval=%s",
        )

    if event is not None:
        await _waiter.discard(approval_id)
        _clear_waiter_heartbeat(approval_id)
    logger.warning("无 SSE 订阅者且不允许离线审批，按拒绝处理: tool=%s", tool_name)
    record.status = AgentApproval.Status.REJECTED
    record.decided_at = timezone.now()
    await record.asave(update_fields=["status", "decided_at"])
    return False, approval_id, record.reason or "无人在线且不允许离线审批，按拒绝处理"


async def decide_approval(
    approval_id: str,
    approved: bool,
    *,
    user_id: int | None = None,
    reason: str = "",
) -> bool:
    """前端提交决定。返回是否成功（找不到等待者时仍更新数据库）。

    ``reason`` 为拒绝理由（可空）：落库到 ``AgentApproval.reason``，并由
    ``request_approval`` 的等待方回传给 pi extension——模型据此换更安全的
    路径，而不是只收到一句干巴巴的「用户拒绝」。
    """
    normalized = approval_id.replace("-", "")
    found = await _waiter.resolve(approval_id, approved) or await _waiter.resolve(normalized, approved)
    # 唤醒可能在其他 worker 上的等待者
    _write_decision(approval_id, approved)
    _write_decision(normalized, approved)

    try:
        record = await AgentApproval.objects.filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        record = None

    # 允许对 **timeout** 的单子补批：MCP 闸门为了不被客户端超时掐断，最多等
    # WAIT(≤150s) 就返回「已发起审批」；律师晚几分钟看到卡片点同意是常态。
    # 不补批的话那张卡永久钉在 timeout，重试只能再弹一张——体验与审计都更差。
    late_answer = record is not None and record.status == AgentApproval.Status.TIMEOUT
    if record is not None and (record.status == AgentApproval.Status.PENDING or late_answer):
        record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        record.decided_at = timezone.now()
        if late_answer and approved:
            # 补批要重新计有效期：DB 台账（MCP 闸门）只在 expires_at 未过期时放行，
            # 而原来那条是按「发起时刻 + 离线超时」算的，早就过期了。
            record.expires_at = timezone.now() + timedelta(seconds=LATE_GRANT_SECONDS)
        if user_id is not None:
            record.decided_by_id = user_id
        if reason.strip():
            # 写 ``decision_reason`` 而不是覆盖 ``reason``：后者是发起方写的
            # 请求理由，覆盖掉后就分不清「为什么提」与「为什么拒」了。
            record.decision_reason = reason.strip()[:2000]
            await record.asave(update_fields=["status", "decided_at", "decided_by", "decision_reason", "expires_at"])
        else:
            await record.asave(update_fields=["status", "decided_at", "decided_by", "expires_at"])

    return found or record is not None
