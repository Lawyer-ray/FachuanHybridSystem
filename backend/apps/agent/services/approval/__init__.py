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

## 子模块

- ``risk``：风险分级权威表（常量 + classify_risk）
- ``annotations``：MCP 工具注解表（懒加载，分级补漏层）
- ``policy``：用户审批策略（P2-5）
- ``waiter``：进程内等待器 + 跨 worker 决定/心跳
- ``flow``：发起 / 等待 / 决定主流程
- ``queries``：审计列表与待办发现

本 ``__init__`` 是门面：重导出原 ``approval.py`` 的全部符号，
``from apps.agent.services.approval import X`` 与 ``approval.X`` 访问不变。
"""

from ..event_bus import redis_cache_enabled
from .annotations import (
    _annotation_table,
    _list_mcp_tools,
    _reset_annotation_cache,
    load_tool_annotations,
    prime_annotation_cache,
)
from .flow import (
    OFFLINE_ENV,
    _approval_message,
    _sse_channel,
    allow_offline_approval,
    decide_approval,
    request_approval,
)
from .policy import lookup_approval_policy
from .queries import get_approval_for_decision, list_approvals, list_pending_for_user
from .risk import (
    APPROVAL_EXEMPT_SUFFIXES,
    CRITICAL_PATTERNS,
    CRITICAL_TIMEOUT,
    DANGER_PATTERNS,
    DEFAULT_TIMEOUT,
    HARD_DENY_PATTERNS,
    OFFLINE_TIMEOUT,
    SENSITIVE_ARG_MARKERS,
    WRITE_PREFIXES,
    RiskLevel,
    _classify_by_annotations,
    _classify_by_name,
    _has_sensitive_arg,
    _worse,
    approval_timeout,
    classify_risk,
    is_high_risk,
    needs_second_confirmation,
)
from .waiter import (
    DECISION_KEY_PREFIX,
    DECISION_POLL_INTERVAL,
    DECISION_TTL,
    WAITER_KEY_PREFIX,
    _ApprovalWaiter,
    _clear_decision,
    _clear_waiter_heartbeat,
    _read_decision,
    _wait_decision,
    _waiter,
    _waiter_is_alive,
    _write_decision,
    _write_waiter_heartbeat,
)

__all__ = [
    # risk
    "DANGER_PATTERNS",
    "APPROVAL_EXEMPT_SUFFIXES",
    "CRITICAL_PATTERNS",
    "HARD_DENY_PATTERNS",
    "SENSITIVE_ARG_MARKERS",
    "WRITE_PREFIXES",
    "DEFAULT_TIMEOUT",
    "CRITICAL_TIMEOUT",
    "OFFLINE_TIMEOUT",
    "RiskLevel",
    "classify_risk",
    "is_high_risk",
    "needs_second_confirmation",
    "approval_timeout",
    "_has_sensitive_arg",
    "_classify_by_name",
    "_classify_by_annotations",
    "_worse",
    # annotations
    "load_tool_annotations",
    "_annotation_table",
    "_list_mcp_tools",
    "_reset_annotation_cache",
    # policy
    "lookup_approval_policy",
    # waiter
    "DECISION_KEY_PREFIX",
    "WAITER_KEY_PREFIX",
    "DECISION_TTL",
    "DECISION_POLL_INTERVAL",
    "_ApprovalWaiter",
    "_waiter",
    "_wait_decision",
    "_write_decision",
    "_read_decision",
    "_clear_decision",
    "_write_waiter_heartbeat",
    "_waiter_is_alive",
    "_clear_waiter_heartbeat",
    "redis_cache_enabled",
    # flow
    "OFFLINE_ENV",
    "allow_offline_approval",
    "request_approval",
    "decide_approval",
    "_sse_channel",
    "_approval_message",
    # queries
    "get_approval_for_decision",
    "list_approvals",
    "list_pending_for_user",
]
