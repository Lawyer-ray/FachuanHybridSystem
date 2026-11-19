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

from ..backends.gateway_cache import load_api_keys
from ..backends.key_scheduler import get_key_scheduler
from ..models import AgentMessage, AgentSession
from ..pi.pool import PoolQueueTimeoutError
from ..pi.rpc_client import parse_context_usage
from .chat import env
from .chat.pool import get_pool
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

    user_token = await env.mint_user_token(user_id)
    session_env = env.session_env(session, user_id, user_token=user_token)

    # 轮次级 key 分配：压缩是**单栏**操作，所以只占一把。
    #
    # 为什么压缩也要参与分配：网关按「每把 key 并发 N」限流，压缩与正常对话
    # 打的是同一批 key。若压缩还走后端自己的 ``_next_key``，它可能正好压在
    # 某个已有 3 个对话在用 key 上 → 429 → 用户看到「压缩卡住 60 秒」，而这一刻
    # 往往正是他上下文快爆了、最需要压缩成功的时候。
    #
    # 拿不到 key 池时 ``load_api_keys`` 返回空元组，``allocate`` 给出空租约，
    # 传给 pool 的就是 ``None`` → 回落后端轮转（引入本机制前的行为）。
    scheduler = get_key_scheduler()
    lease = scheduler.allocate(await load_api_keys(getattr(session, "llm_model", "") or None), 1)[0]
    try:
        pool = await get_pool()
        async with pool.acquire(
            session_env=session_env, session_id=session_id, api_key=lease.key or None
        ) as pi_session:
            await pi_session.compact()
            stats = await pi_session.get_session_stats()
    except PoolQueueTimeoutError as exc:
        raise CompactBusyError("当前使用人数较多，请稍后再试") from exc
    finally:
        # 必须归还：漏一次就把这把 key 的一个并发槽永久占掉，之后越来越容易 429。
        lease.release()

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
