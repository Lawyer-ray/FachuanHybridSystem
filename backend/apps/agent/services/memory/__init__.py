"""Agent 记忆服务 —— 检索、注入渲染、策展提升、自动抽取、行为推断。

## 分层职责

本包是记忆能力的**唯一业务入口**：MCP 工具面、REST API、django-q 任务、
pi 扩展注入的快照端点全部经此。好处是权限过滤只有一处实现，不会出现
「工具面按人过滤、注入端点忘了过滤」这类越权。

## 子域布局（原 memory_service.py 拆分）

- ``scopes``：作用域解析与权限边界（``visible_queryset`` 是唯一读入口）
- ``search``：语义 + 关键词混合检索与命中计数
- ``snapshot``：注入渲染、配额常量、缓存与失效
- ``write``：创建 / 确认 / 软删 / 恢复（content_hash 在写入口派生）
- ``curation``：策展候选池、强制改写与 PII 闸门
- ``extraction``：会话结束后的 LLM 异步抽取
- ``behavior``：零 LLM 的审计数据行为推断

依赖向：scopes ← search/snapshot/write/curation；write → snapshot/search；
curation → write + scopes + snapshot；extraction/behavior → write。
本 ``__init__`` 是纯门面：重导出全部公开符号，旧导入路径
``apps.agent.services.memory_service`` 经 ``services/__init__`` 的别名与
下方 ``sys.modules`` 注册继续可用（调用方按模块属性访问，必须保留）。

## 注入为什么要快照 + 缓存

记忆块若每轮重算并拼进 system prompt，前缀每轮都变，**prompt cache 全废**
（这是 ``backend/apps/agent/README.md`` 大篇幅论证过的性能点）。
所以渲染出的快照按会话缓存，只在 pi 扩展的
``session_start`` / ``session_before_compact`` / 长期记忆写入 / 跨天时失效。

缓存落 Django cache（Redis 或 locmem），不用进程内变量：``pool.acquire()``
每请求起一个新 pi 进程，进程内变量根本跨不了轮次。

## 团队/律所为什么是「提升」不是「合并」

见 ``models/memory.py`` 的模块注释。这里补一句实现上的对应：
``promote_memory()`` 要求管理员**改写内容**（``content`` 必传且必须与原记忆
不同），并跑 ``scan_pii_risk()``。这两步就是脱敏闸门，不是可选装饰。
"""

from __future__ import annotations

import logging
import sys

from ...models import AgentMemory, AgentSession, content_hash_of
from .behavior import derive_preferences_from_behavior, persist_suggestions
from .curation import promote_candidates, promote_memory, scan_pii_risk
from .extraction import MAX_EXTRACT_ITEMS, extract_memories_from_session
from .payloads import curatable_scopes_payload, list_memories_payload, memory_to_dict, search_memories_payload
from .scopes import anchor_visible_queryset, can_curate_scope, resolve_scopes, team_member_ids, visible_queryset
from .search import MIN_RELATIVE_RATIO, MIN_SIMILARITY, mark_hit, search_memories
from .snapshot import (
    INDEX_QUOTA,
    INJECT_QUOTA_LAW_FIRM,
    INJECT_QUOTA_LAWYER,
    INJECT_QUOTA_PROJECT_FACT,
    INJECT_QUOTA_PROJECT_JUDGMENT,
    INJECT_QUOTA_TEAM,
    MAX_SINGLE_ENTRY_CHARS,
    PLAYBOOK_MAX_CHARS,
    SNAPSHOT_CACHE_KEY,
    SNAPSHOT_CACHE_TTL,
    SnapshotLayer,
    build_snapshot,
    invalidate_snapshot,
)
from .write import (
    NOTE_MAX_CHARS,
    confirm_memories,
    confirm_note,
    create_memory,
    create_note,
    forget_memory,
    restore_memory,
)

logger = logging.getLogger(__name__)

# 旧模块路径兼容：原 memory_service.py 已拆为本包。注册模块别名，使
# `from apps.agent.services.memory_service import X` 与
# `import apps.agent.services.memory_service as m` 两种旧写法继续可用；
# `from apps.agent.services import memory_service` 由 services/__init__ 别名承接。
sys.modules[f"{__name__.rsplit('.', 1)[0]}.memory_service"] = sys.modules[__name__]

__all__ = [
    # 模块级 logger（原模块公开属性，保持兼容）
    "logger",
    # 模型符号（原模块导入面，保持属性兼容）
    "AgentMemory",
    "AgentSession",
    "content_hash_of",
    # 配额与检索常量
    "INJECT_QUOTA_LAWYER",
    "INJECT_QUOTA_TEAM",
    "INJECT_QUOTA_LAW_FIRM",
    "MAX_SINGLE_ENTRY_CHARS",
    "INDEX_QUOTA",
    "PLAYBOOK_MAX_CHARS",
    "MAX_EXTRACT_ITEMS",
    "MIN_SIMILARITY",
    "MIN_RELATIVE_RATIO",
    "SNAPSHOT_CACHE_TTL",
    "SNAPSHOT_CACHE_KEY",
    "INJECT_QUOTA_PROJECT_FACT",
    "INJECT_QUOTA_PROJECT_JUDGMENT",
    "NOTE_MAX_CHARS",
    # 作用域与权限
    "resolve_scopes",
    "visible_queryset",
    "can_curate_scope",
    "team_member_ids",
    "anchor_visible_queryset",
    # 检索
    "search_memories",
    "mark_hit",
    # 注入快照
    "SnapshotLayer",
    "build_snapshot",
    "invalidate_snapshot",
    # 写入
    "create_memory",
    "create_note",
    "confirm_note",
    "confirm_memories",
    "forget_memory",
    "restore_memory",
    # 策展
    "promote_candidates",
    "promote_memory",
    "scan_pii_risk",
    # 抽取与行为推断
    "extract_memories_from_session",
    "derive_preferences_from_behavior",
    "persist_suggestions",
    # API 读侧载荷（业务逻辑下沉，API 层只装 Schema）
    "memory_to_dict",
    "list_memories_payload",
    "search_memories_payload",
    "curatable_scopes_payload",
]
