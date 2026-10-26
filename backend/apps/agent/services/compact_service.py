"""手动压缩会话上下文（`POST /sessions/{id}/compact` 的服务层）。

## 为什么手动压缩值得一个独立入口

自动压缩按水位阈值触发（settings.json 的 compaction 配置），律师无法在
「马上要开长任务」前主动腾空间。pi 的 RPC ``compact`` 是同步命令（压缩
完成才返回），走一次进程池 acquire（``--session-id`` 续写既有 session
文件）即可，不需要对话在跑。

## 与压缩接管 extension 的关系

``pi/compaction-takeover.ts`` 挂在 pi 的 ``session_before_compact`` 钩子上，
手动压缩与自动压缩走同一个确定性编译器（保案号/当事人/金额/期限锚点），
失败自动回退 pi 原生 LLM 摘要——两条路径摘要质量一致，无需区分。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

from ..models import AgentMessage, AgentSession
from ..pi.pool import PoolQueueTimeoutError
from ..pi.rpc_client import PiError, parse_context_usage
from .chat_service import _mint_user_token, _session_env, get_pool
from .session_cleanup import has_pi_session

logger = logging.getLogger(__name__)


class CompactNotNeededError(RuntimeError):
    """会话没有可压缩的历史（还没有 pi session 文件）。"""


class CompactBusyError(RuntimeError):
    """进程池忙（排队超时）——稍后再试，不是故障。"""


async def compact_session(*, session: AgentSession, user_id: int | None) -> dict[str, Any]:
    """压缩一个会话的上下文并返回新水位。

    Raises:
        CompactNotNeededError: 会话还没有 pi session 历史。
        CompactBusyError: 进程池排队超时。
        PiError: pi 运行失败（含压缩被拒）。
    """
    session_id = str(session.session_id)
    if not await sync_to_async(has_pi_session, thread_sensitive=True)(session_id):
        raise CompactNotNeededError("会话还没有对话历史，无需压缩")

    user_token = await _mint_user_token(user_id)
    session_env = _session_env(session, user_id, user_token=user_token)
    try:
        pool = await get_pool()
        async with pool.acquire(session_env=session_env, session_id=session_id) as pi_session:
            await pi_session.compact()
            stats = await pi_session.get_session_stats()
    except PoolQueueTimeoutError as exc:
        raise CompactBusyError("当前使用人数较多，请稍后再试") from exc

    used, total = parse_context_usage(stats)
    try:
        await AgentMessage.objects.acreate(
            session=session,
            role=AgentMessage.Role.TOOL,
            content="手动压缩上下文",
            tool_name="context_compaction",
            metadata={"context_used_tokens": used, "context_total_tokens": total},
        )
    except Exception:
        logger.warning("压缩审计消息落库失败（不影响压缩结果）", exc_info=True)
    logger.info(
        "手动压缩完成 session=%s 新水位=%s/%s",
        session_id,
        used,
        total,
    )
    return {
        "compacted": True,
        "context_used_tokens": used,
        "context_total_tokens": total,
    }
