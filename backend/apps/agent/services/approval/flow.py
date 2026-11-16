"""审批主流程 —— 发起审批、阻塞等待、提交决定（fail-closed）。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone

from ...models import AgentApproval, AgentSession
from ..event_bus import redis_cache_enabled
from .policy import lookup_approval_policy
from .risk import OFFLINE_TIMEOUT, RiskLevel, approval_timeout, classify_risk, needs_second_confirmation
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


def _approval_message(tool_name: str, level: RiskLevel) -> str:
    """给前端弹窗用的提示语（按等级区分措辞，避免一律「高风险」而失去区分度）。"""
    short = tool_name.rsplit("__", 1)[-1]
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
        record.decided_at = timezone.now()
        await record.asave(update_fields=["status", "decided_at"])
    reason_out = record.reason or ("用户同意" if record.is_granted else "用户拒绝或超时")
    return record.is_granted, approval_id, reason_out


async def request_approval(
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    reason: str = "",
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
        has_remote = bool(await bus.has_subscribers(session_id)) or redis_cache_enabled()
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

    if record is not None and record.status == AgentApproval.Status.PENDING:
        record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        record.decided_at = timezone.now()
        if user_id is not None:
            record.decided_by_id = user_id
        if reason.strip():
            record.reason = reason.strip()[:2000]
            await record.asave(update_fields=["status", "decided_at", "decided_by", "reason"])
        else:
            await record.asave(update_fields=["status", "decided_at", "decided_by"])

    return found or record is not None
