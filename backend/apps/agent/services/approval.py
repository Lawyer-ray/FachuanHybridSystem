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

1. extension 侧 ``HIGH_RISK_PATTERNS`` 命中即回调
2. 服务端 ``DANGER_PATTERNS`` 二次判定，即便 extension 被绕过也拦得住

两侧模式清单的一致性、以及清单对 ``mcp_server`` 实际工具注册表的覆盖，
由 ``tests/ci/unit/agent/test_agent_runtime.py`` 守护。
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
from .event_bus import redis_cache_enabled

logger = logging.getLogger(__name__)

#: 高危工具判定模式（对完整工具名做子串匹配；pi 侧形如 ``mcp__fachuan__delete_lawyer``）。
#: 模式从 mcp_server 实际注册表校准——旧清单 6 个名字里有 3 个（send_document /
#: file_lawsuit / submit_court_document）在 378 个工具中根本不存在，而 39 个
#: ``delete_*`` 只拦住 8 个：
#: - ``delete`` / ``remove_`` / ``destroy``：一切删除操作
#: - ``send_`` / ``submit_`` / ``upload_`` / ``file_``：对外发出、递交、上传（不可撤回）
#: - ``confirm_``：如 confirm_archive（OA 归档确认）
#: - ``clear_all`` / ``reset_and_``：批量清空 / 重置
#: 刻意**不**拦 ``create_`` / ``update_``（常规业务写由各域服务层归属校验兜底，
#: 逐笔审批会让 agent 不可用）与 ``sync_`` / ``export_`` / ``download_``（拉取导出，无破坏性）。
DANGER_PATTERNS: tuple[str, ...] = (
    "delete",
    "remove_",
    "destroy",
    "send_",
    "submit_",
    "upload_",
    "file_",
    "confirm_",
    "clear_all",
    "reset_and_",
)

#: 已知无需审批的例外（按工具名后缀登记；新增例外必须写明理由）。
APPROVAL_EXEMPT_SUFFIXES: frozenset[str] = frozenset()

DEFAULT_TIMEOUT = 300.0


def is_high_risk(tool_name: str) -> bool:
    """工具名是否属于高危（子串模式匹配，pi 侧是 ``mcp__fachuan__<name>`` 形式）。"""
    if any(tool_name.endswith(suffix) for suffix in APPROVAL_EXEMPT_SUFFIXES):
        return False
    return any(pattern in tool_name for pattern in DANGER_PATTERNS)


DECISION_KEY_PREFIX = "agent:approval:decision:"
DECISION_TTL = 600
DECISION_POLL_INTERVAL = 0.2


def _write_decision(approval_id: str, approved: bool) -> None:
    """把决定写入 Redis，供**其他 worker** 上的等待者读取。

    等待审批的 HTTP 请求和「用户点同意」的 HTTP 请求可能落在不同 worker，
    而 ``_ApprovalWaiter`` 是进程内的。没有这一步，跨 worker 时等待方永远
    等不到结果，只能超时走 fail-closed（表现为「审批了但工具没执行」）。
    """
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.set(f"{DECISION_KEY_PREFIX}{approval_id}", "1" if approved else "0", DECISION_TTL)
    except Exception:
        logger.debug("写入审批决定失败: %s", approval_id, exc_info=True)


def _read_decision(approval_id: str) -> bool | None:
    """读取其他 worker 写入的决定；无则返回 ``None``。"""
    if not redis_cache_enabled():
        return None
    from django.core.cache import cache

    try:
        raw = cache.get(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        return None
    if raw is None:
        return None
    return str(raw) == "1"


def _clear_decision(approval_id: str) -> None:
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.delete(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        logger.debug("清理审批决定键失败（可忽略）: %s", approval_id, exc_info=True)


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

    # 先登记等待者、再 publish。反过来的话，若「用户决定」先于 register 到达
    # （自动审批 / 前端重试），resolve 找不到等待者只能落库 approved，等待方
    # 却等不到事件，最终超时分支会把已 approved 的记录覆盖成 timeout——
    # 用户点了同意、工具却被拒。
    delivered = 0
    has_remote = False
    event: asyncio.Event | None = None
    if session_id:
        event = await _waiter.register(approval_id)
        from .event_bus import get_bus

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
                "message": reason or f"即将执行高风险操作：{tool_name}，请确认是否继续",
            },
        )

    if event is not None and (delivered or has_remote):
        try:
            approved = await _wait_decision(approval_id, event, timeout)
            record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        except TimeoutError:
            record.status = AgentApproval.Status.TIMEOUT
            logger.info("审批超时，按拒绝处理: tool=%s approval=%s", tool_name, approval_id)
        finally:
            await _waiter.discard(approval_id)
            _clear_decision(approval_id)
            record.decided_at = timezone.now()
            await record.asave(update_fields=["status", "decided_at"])
        return record.is_granted, approval_id

    # 没有订阅者：无人可问 → fail-closed
    if event is not None:
        await _waiter.discard(approval_id)
    logger.warning("无 SSE 订阅者，审批按拒绝处理: tool=%s", tool_name)
    record.status = AgentApproval.Status.REJECTED
    record.decided_at = timezone.now()
    await record.asave(update_fields=["status", "decided_at"])
    return False, approval_id


async def _wait_decision(approval_id: str, event: asyncio.Event, timeout: float) -> bool:
    """等审批结果：本进程有人点就立即醒，否则轮询 Redis（跨 worker）。

    Returns:
        是否放行。

    Raises:
        TimeoutError: 超时未决。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        if event.is_set():
            return await _waiter.take_result(approval_id)

        remote = _read_decision(approval_id)
        if remote is not None:
            return remote

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError

        try:
            await asyncio.wait_for(event.wait(), timeout=min(DECISION_POLL_INTERVAL, remaining))
        except TimeoutError:
            continue


async def decide_approval(
    approval_id: str,
    approved: bool,
    *,
    user_id: int | None = None,
) -> bool:
    """前端提交决定。返回是否成功（找不到等待者时仍更新数据库）。"""
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
        await record.asave(update_fields=["status", "decided_at", "decided_by"])

    return found or record is not None


async def get_approval_for_decision(approval_id: str) -> AgentApproval | None:
    """取审批记录（含会话预取）供归属判定；无效 id 返回 None。"""
    try:
        normalized = approval_id.replace("-", "")
        return await AgentApproval.objects.select_related("session").filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        return None


async def list_approvals(*, user: Any, limit: int) -> list[AgentApproval]:
    """审批记录列表（审计用；非超级用户仅见自己会话的记录）。"""
    queryset = AgentApproval.objects.all()
    if user is not None and not getattr(user, "is_superuser", False):
        queryset = queryset.filter(session__user_id=user.pk)
    return [record async for record in queryset[: max(1, min(limit, 200))]]
