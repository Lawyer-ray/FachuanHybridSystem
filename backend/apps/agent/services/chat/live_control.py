"""运行中插话（steer / follow_up / clear_queue）。"""

from __future__ import annotations

import logging

from ..live_sessions import get_live_registry

logger = logging.getLogger(__name__)


class SessionNotLiveError(RuntimeError):
    """会话当前没有运行中的 pi 进程（没在跑，或跑在别的 worker 上）。"""


async def steer_session(*, session_id: str, message: str) -> str:
    """运行中插话：当前 assistant turn 的工具调用跑完后、下次 LLM 调用前生效。

    Raises:
        SessionNotLiveError: 会话没在跑（本实例内找不到）。
        PiError: pi 拒绝（例如已 settle）。
    """
    pi_session = await get_live_registry().get(session_id)
    if pi_session is None:
        raise SessionNotLiveError("会话当前没有运行中的对话")
    disposition: str = await pi_session.steer(message)
    logger.info("steer 已投递 session=%s disposition=%s", session_id, disposition)
    return disposition


async def follow_up_session(*, session_id: str, message: str) -> str:
    """追加一轮：agent 干完当前所有活（无工具调用、无 steering）后再跑。

    Raises:
        SessionNotLiveError: 会话没在跑。
        PiError: pi 拒绝。
    """
    pi_session = await get_live_registry().get(session_id)
    if pi_session is None:
        raise SessionNotLiveError("会话当前没有运行中的对话")
    disposition: str = await pi_session.follow_up(message)
    logger.info("follow_up 已投递 session=%s disposition=%s", session_id, disposition)
    return disposition


async def clear_queue_session(*, session_id: str) -> list[str]:
    """撤回已排队但尚未生效的 steering / follow-up 消息，返回其文本。

    会话没在跑时返回空列表（没有队列可清），不算错误——前端「撤销」按钮
    点击时可能刚好上一轮已结束。
    """
    pi_session = await get_live_registry().get(session_id)
    if pi_session is None:
        return []
    texts: list[str] = await pi_session.clear_queue()
    if texts:
        logger.info("clear_queue 撤回 %s 条 session=%s", len(texts), session_id)
    return texts
