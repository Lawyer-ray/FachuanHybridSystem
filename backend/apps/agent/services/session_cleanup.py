"""pi session 与 Django 会话的生命周期对齐。

Django 的 ``AgentMessage`` 是审计权威，pi 的 session 文件是**模型上下文**的
载体。两者必须同步：删除会话只删数据库会留下模型上下文（含工具调用参数、
工具返回的业务数据），用户以为删干净了其实没有。

这里只做「跨层对齐」，文件操作本身在 ``pi/session_store.py``。
"""

from __future__ import annotations

import logging

from ..pi.session_store import delete_session as _delete_pi_session
from ..pi.session_store import has_session as _has_session
from ..pi.session_store import purge_orphans as _purge_orphans

logger = logging.getLogger(__name__)


def has_pi_session(session_id: str) -> bool:
    """该会话是否已有 pi 原生 session（决定续写还是回退 transcript）。"""
    try:
        return _has_session(session_id)
    except Exception:
        # 目录不可读等异常不应阻断对话：当作「没有」走回退路径
        logger.warning("检查 pi session 失败 session=%s", session_id, exc_info=True)
        return False


def delete_pi_session(session_id: str) -> int:
    """删除会话时同步清理 pi session 文件，返回清理的文件数。"""
    try:
        return _delete_pi_session(session_id)
    except Exception:
        # 清理失败不能回滚「删会话」本身（用户意图明确），但要留下线索
        logger.warning("清理 pi session 失败 session=%s", session_id, exc_info=True)
        return 0


def purge_orphan_pi_sessions(valid_session_ids: list[str]) -> int:
    """清理不属于任何现存会话的 pi session 目录（运维定时任务用）。"""
    return _purge_orphans(set(valid_session_ids))
