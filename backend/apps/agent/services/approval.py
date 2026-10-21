"""审批服务 —— 高风险工具调用的人机确认。

## 链路

    pi tool_call 钩子
      → POST /api/v1/agent/approval/request   （extension 发问，同步阻塞）
      → 建 AgentApproval(pending) + 推 SSE approval_request 给前端
      → 用户点同意/拒绝 → POST /api/v1/agent/approval/{id}/decide
      → 返回 {"approved": bool} 给 extension
      → extension 放行或 block

## fail-closed

只有 ``approved`` 是放行。超时 / 用户离开 / 服务异常 / SSE 通道不可用，
一律按拒绝处理：

- 内存等待器超时 → 落库 ``timeout``，返回 False
- 无 SSE 通道（例如后台任务触发）→ 直接拒绝，不静默放行
- 工具名不在清单内 → 放行（非高危）

## 两层防护

1. extension 侧 ``HIGH_RISK_TOOLS`` 命中即回调
2. 服务端 ``HIGH_RISK_TOOLS`` 二次判定，即便 extension 被绕过也拦得住

两份清单的一致性由 ``tests/ci/unit/agent/test_approval.py`` 守护。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from django.utils import timezone

from ..models import AgentApproval, AgentSession

logger = logging.getLogger(__name__)

#: 必须人工审批的高危工具。与 pi extension 侧清单保持一致。
HIGH_RISK_TOOLS: frozenset[str] = frozenset(
    {
        "delete_case",
        "delete_client",
        "delete_contract",
        "send_document",
        "file_lawsuit",
        "submit_court_document",
    }
)

DEFAULT_TIMEOUT = 300.0


def is_high_risk(tool_name: str) -> bool:
    """工具名是否属于高危（pi 侧是 ``mcp__fachuan__<name>`` 形式，用包含匹配）。"""
    return any(marker in tool_name for marker in HIGH_RISK_TOOLS)


class _ApprovalWaiter:
    """进程内等待器：把「前端点了什么」交回给阻塞的 HTTP 请求。

    只做进程内协调，**状态真相在数据库**。这样即便进程重启，
    历史审批仍可审计；只是进行中的等待会随进程消失（客户端得到超时 → 拒绝）。
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, bool] = {}
        self._lock = asyncio.Lock()

    async def register(self, approval_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._events[approval_id] = event
            self._results[approval_id] = False
            return event

    async def resolve(self, approval_id: str, approved: bool) -> bool:
        """前端决定后调用；返回是否找到等待者。"""
        async with self._lock:
            event = self._events.get(approval_id)
            if event is None:
                return False
            self._results[approval_id] = approved
            event.set()
            return True

    async def take_result(self, approval_id: str) -> bool:
        async with self._lock:
            return self._results.get(approval_id, False)

    async def discard(self, approval_id: str) -> None:
        async with self._lock:
            self._events.pop(approval_id, None)
            self._results.pop(approval_id, None)


_waiter = _ApprovalWaiter()


@asynccontextmanager
async def _sse_channel(
    session_id: str | None,
) -> AsyncIterator[asyncio.Queue[dict[str, Any]] | None]:
    """登记 SSE 通道；无会话上下文时给出 ``None``（调用方按拒绝处理）。"""
    from .event_bus import get_bus

    if not session_id:
        yield None
        return
    queue = await get_bus().register(session_id)
    try:
        yield queue
    finally:
        await get_bus().unregister(session_id, queue)


async def request_approval(
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    reason: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[bool, str]:
    """发起一次审批并阻塞等待。

    Returns:
        ``(approved, approval_id)``。``approved`` 为 ``True`` 才放行。
    """
    approval_id = uuid.uuid4().hex

    if not is_high_risk(tool_name):
        return True, approval_id

    session = None
    if session_id:
        try:
            session = await AgentSession.objects.filter(session_id=session_id).afirst()
        except Exception:
            logger.debug("按 session_id 查会话失败: %s", session_id, exc_info=True)

    record = await AgentApproval.objects.acreate(
        approval_id=uuid.UUID(approval_id),
        session=session,
        tool_name=tool_name,
        tool_args=tool_args or {},
        reason=reason,
    )

    # 推给该会话的所有 SSE 订阅者。注意**不能自己 register 一个队列再 put**：
    # 那会与 chat_service 的 SSE 循环各持一个队列，事件永远送不到前端。
    # 这里统一走 bus.publish，送到真实订阅者。
    from .event_bus import get_bus

    delivered = 0
    if session_id:
        delivered = await get_bus().publish(
            session_id,
            {
                "type": "approval_request",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "tool_args": tool_args or {},
                "message": reason or f"即将执行高风险操作：{tool_name}，请确认是否继续",
            },
        )

    if session_id and delivered:
        event = await _waiter.register(approval_id)
        approved = False
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            approved = await _waiter.take_result(approval_id)
            record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        except TimeoutError:
            record.status = AgentApproval.Status.TIMEOUT
            logger.info("审批超时，按拒绝处理: tool=%s approval=%s", tool_name, approval_id)
        finally:
            await _waiter.discard(approval_id)
            record.decided_at = timezone.now()
            await record.asave(update_fields=["status", "decided_at"])
        return record.is_granted, approval_id

    # 没有订阅者：无人可问 → fail-closed
    logger.warning("无 SSE 订阅者，审批按拒绝处理: tool=%s", tool_name)
    record.status = AgentApproval.Status.REJECTED
    record.decided_at = timezone.now()
    await record.asave(update_fields=["status", "decided_at"])
    return False, approval_id


async def decide_approval(
    approval_id: str,
    approved: bool,
    *,
    user_id: int | None = None,
) -> bool:
    """前端提交决定。返回是否成功（找不到等待者时仍更新数据库）。"""
    normalized = approval_id.replace("-", "")
    found = await _waiter.resolve(approval_id, approved) or await _waiter.resolve(normalized, approved)

    try:
        record = await AgentApproval.objects.filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        record = None

    if record is not None and record.status == AgentApproval.Status.PENDING:
        record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        record.decided_at = timezone.now()
        if user_id is not None:
            record.decided_by_id = user_id
        await record.asave(update_fields=["status", "decided_at", "decided_by"])

    return found or record is not None
