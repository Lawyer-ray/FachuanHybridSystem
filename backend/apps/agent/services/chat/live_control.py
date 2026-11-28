"""运行中插话（steer / follow_up / clear_queue）。

## 为什么插话也要过 ``/skill:`` 展开

运行中插话是**第 7 条**消息入口：它不走 ``stream_chat``，所以 ``prepare_context``
的展开覆盖不到它。律师在模型已经跑到一半时敲 ``/skill:contract-review 只看违约条款``，
期望的是与正常发送完全一样的语义；漏掉这一路的症状是「同样一条命令，发消息时好
使、插话时静默失效」。这里只展开、不碰索引块：索引块是**开轮**时算的，插话在
同一轮内，重建它只会把系统提示的缓存前缀打乱。
"""

from __future__ import annotations

import logging

from asgiref.sync import sync_to_async

from ..live_sessions import get_live_registry
from ..skills.expand import expand_skill_prompt

logger = logging.getLogger(__name__)


class SessionNotLiveError(RuntimeError):
    """会话当前没有运行中的 pi 进程（没在跑，或跑在别的 worker 上）。"""


async def steer_session(*, session_id: str, message: str, user_id: int | None = None) -> str:
    """运行中插话：当前 assistant turn 的工具调用跑完后、下次 LLM 调用前生效。

    Args:
        user_id: 当前用户 id；用于 ``/skill:`` 展开时的可见技能解析。``None``
            （无身份 / 旧调用方）时只认内置技能，不报错。

    Raises:
        SessionNotLiveError: 会话没在跑（本实例内找不到）。
        PiError: pi 拒绝（例如已 settle）。
    """
    pi_session = await get_live_registry().get(session_id)
    if pi_session is None:
        raise SessionNotLiveError("会话当前没有运行中的对话")
    expanded = await _expand(user_id=user_id, message=message)
    disposition: str = await pi_session.steer(expanded)
    logger.info("steer 已投递 session=%s disposition=%s", session_id, disposition)
    return disposition


async def follow_up_session(*, session_id: str, message: str, user_id: int | None = None) -> str:
    """追加一轮：agent 干完当前所有活（无工具调用、无 steering）后再跑。

    Args:
        user_id: 当前用户 id（同 :func:`steer_session`）。

    Raises:
        SessionNotLiveError: 会话没在跑。
        PiError: pi 拒绝。
    """
    pi_session = await get_live_registry().get(session_id)
    if pi_session is None:
        raise SessionNotLiveError("会话当前没有运行中的对话")
    expanded = await _expand(user_id=user_id, message=message)
    disposition: str = await pi_session.follow_up(expanded)
    logger.info("follow_up 已投递 session=%s disposition=%s", session_id, disposition)
    return disposition


async def _expand(*, user_id: int | None, message: str) -> str:
    """把插入消息里的 ``/skill:`` 展开成 ``<skill>`` 块；未命中原样返回。

    ``expand_skill_prompt`` 内部走同步 ORM（``resolve_for_user``），而这里在异步
    上下文——必须放线程里跑，否则 ``SynchronousOnlyOperation`` 会让插话直接 500。
    """
    expanded = await sync_to_async(expand_skill_prompt, thread_sensitive=True)(user_id=user_id, text=message)
    return expanded.prompt


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
