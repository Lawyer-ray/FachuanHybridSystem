"""Agent 对话编排 —— 把一次对话跑在 pi 上。

## 与 apps.workbench 的关系

完全独立：不使用 workbench 的模型、服务或 ContextVar。
（workbench 已于 v27.7.20 整体移除，本 app 是唯一的 AI 对话运行时。）

## 并发模型

- 每个请求从进程池借一个 pi 进程，用完归还
- 事件经 ``event_bus`` 按会话分发（审批回调也是这条通道）
- 会话历史存 Django，pi 以 ``--no-session`` 运行，不持有状态

## 事件契约

    activity → delta* → tool_call*/tool_result* → usage* → approval_request? → error? → done

## 子模块

- ``pool``：pi 进程池单例与配置解析
- ``env``：会话级环境变量与用户凭证铸造（compact_service 复用）
- ``persist``：消息 / 运行记录落库
- ``stream``：stream_chat 主编排
- ``multi``：同一问题同时问 N 个 agent 的合并编排（stream_multi）
- ``dual``：``multi`` 的两栏兼容壳（旧前端 ``dual=true`` 契约）
- ``budget``：按用途（primary / aux）的准入判定与降级
- ``live_control``：运行中插话（steer / follow_up / clear_queue）

本 ``__init__`` 重导出原 ``chat_service`` 的全部公开符号；``chat_service.py``
门面再从这里转发，保证旧导入路径不变。
"""

from __future__ import annotations

from ...models import AgentMessage, AgentRun, AgentSession
from ...pi.bridge import stream_events
from ...pi.pool import PiProcessPool, PoolConfig, PoolQueueTimeoutError
from ...pi.rpc_client import PiError, PiNotAvailableError, parse_context_usage
from ...pi.shared_mcp import resolve_endpoint, shared_enabled
from ...pi.user_token import USER_TOKEN_ENV, mint_user_access_token
from ..event_bus import get_bus
from ..history import render_transcript
from ..live_sessions import get_live_registry
from ..memory_tasks import enqueue_extraction
from ..session_cleanup import has_pi_session
from ..skill_service import enabled_skill_paths
from .dual import stream_dual
from .env import _worker_id
from .env import mint_user_token
from .env import mint_user_token as _mint_user_token
from .env import session_env
from .env import session_env as _session_env
from .live_control import SessionNotLiveError, clear_queue_session, follow_up_session, steer_session
from .multi import (
    ACTIVITY_DEGRADED,
    MAX_ANSWERS,
    AgentSpec,
    StreamMemo,
    normalize_agents,
    pick_secondary,
    resolve_specs,
    stream_multi,
)
from .persist import _log_task_failure, _persist_compaction_message, _persist_tool_message, _recent_history, _record_run
from .pool import (
    DEFAULT_POOL_SIZE,
    MAX_POOL_SIZE,
    _pool,
    _pool_lock,
    _resolve_model,
    _resolve_pool_size,
    _resolve_queue_timeout,
    close_pool,
    get_pool,
)
from .stream import AUTO_TITLE_LIMIT, auto_title, record_user_message, stream_chat

__all__ = [
    # stream
    "stream_chat",
    "AUTO_TITLE_LIMIT",
    "auto_title",
    "record_user_message",
    # multi / dual
    "MAX_ANSWERS",
    "AgentSpec",
    "normalize_agents",
    "resolve_specs",
    "stream_dual",
    "stream_multi",
    "pick_secondary",
    "ACTIVITY_DEGRADED",
    "StreamMemo",
    # live_control
    "SessionNotLiveError",
    "steer_session",
    "follow_up_session",
    "clear_queue_session",
    # pool
    "get_pool",
    "close_pool",
    "DEFAULT_POOL_SIZE",
    "MAX_POOL_SIZE",
    "_pool",
    "_pool_lock",
    "_resolve_pool_size",
    "_resolve_model",
    "_resolve_queue_timeout",
    # env（公开名 + 兼容旧私有名）
    "session_env",
    "mint_user_token",
    "_session_env",
    "_mint_user_token",
    "_worker_id",
    # persist
    "_record_run",
    "_persist_tool_message",
    "_persist_compaction_message",
    "_recent_history",
    "_log_task_failure",
    # 原模块导入的共享符号（接线断言 / 测试桩仍按原名取）
    "AgentMessage",
    "AgentRun",
    "AgentSession",
    "stream_events",
    "PiProcessPool",
    "PoolConfig",
    "PoolQueueTimeoutError",
    "PiError",
    "PiNotAvailableError",
    "parse_context_usage",
    "resolve_endpoint",
    "shared_enabled",
    "USER_TOKEN_ENV",
    "mint_user_access_token",
    "get_bus",
    "render_transcript",
    "get_live_registry",
    "enqueue_extraction",
    "has_pi_session",
    "enabled_skill_paths",
]
