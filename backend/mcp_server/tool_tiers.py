"""工具面分层 —— 「高频直连 + 长尾按需」。

## 为什么需要分层

2026-10-25 实测：415 个工具的 `tools/list` schema 是 **235 KB / 18.3 万字符**，
按 chars/4~chars/2 口径是 **4.6 万 ~ 9.2 万 token**，而这份 schema 是**每一轮
模型请求都要重发的固定前缀**（工具循环里每轮都付）。

对照：律师一次对话真正会用到的工具，通常不超过 15 个。剩下的 400 个
schema 是纯成本。

## 分层口径

| 层 | 数量 | pi exposure | 说明 |
|:-|:-|:-|:-|
| `direct` | ~30 | 声明给模型 | 最高频的读取 + 全部破坏性工具 |
| `deferred` | 其余 | 不声明，`tool_search` 加载后**以真名**调用 | 长尾业务工具 |

**为什么破坏性工具必须留在 `direct`**：律师要能一眼看见"这个 AI 有删除能力"，
而且审批弹窗里显示的工具名必须与模型选的是同一个。把它们藏起来只会让
风险不可见，不会降低风险。

**为什么走 `deferred` 而不是自建通用分发代理**：`deferred` 由 pi 的
`tool_search` 加载后**仍以真名调用**，审批网关按 `mcp__fachuan__delete_case`
这类全名匹配，判级链路完全不受影响。而"一个 `fachuan_tool_call({name,args})`
通用代理"会让 `tool_call` 钩子只看到 `fachuan_tool_call`（低风险 → 放行），
**等于把四级审批全部关掉**。这条路明确禁止。

## 与审批的关系

分层只改"模型看得到什么"，不改"能执行什么"、也不改"要不要审批"。
`deferred` 工具加载后仍会经过 `approval-gate.ts` 的完整判定。

## 灰度

`FACHUAN_MCP_TOOL_TIERS=off` 回到全量 `direct`（现状行为），用于出问题
时一键回滚。默认 `on`。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

TOOL_TIERS_ENV = "FACHUAN_MCP_TOOL_TIERS"

#: 直连工具清单。选取标准（缺一不可）：
#: 1. 律师对话高频（身份/时间/期限/案件/合同/文书/检索/技能/附件）
#: 2. 或破坏性（必须让模型和律师都看得见）
#: 3. 或元工具（技能索引、任务查询）
#:
#: 刻意**不含** create_/update_ 这类写工具：它们低频且可经 tool_search 找到，
#: 而律师对"AI 能改什么"的预期来自审批弹窗而不是工具清单。
DIRECT_TOOLS: frozenset[str] = frozenset(
    {
        # --- 元信息：每轮几乎都会用到 ---
        "get_current_user",
        "get_server_time",
        "get_agent_skill",
        # --- 案件：最核心的业务对象 ---
        "list_cases",
        "get_case",
        "search_cases",
        # --- 合同 ---
        "list_contracts",
        "get_contract",
        # --- 期限 / 提醒：法律事务里最刚性的一类 ---
        "list_all_reminders",
        "get_reminder",
        "list_upcoming_deadlines",
        # --- 文书 / 材料 ---
        "list_document_templates",
        "get_document_template",
        "read_agent_attachment",
        # --- 检索 ---
        "web_search",
        "fetch_url",
        # --- 汇总 ---
        "get_dashboard_stats",
    }
)

#: 破坏性工具一律直连（模式匹配，覆盖 41 个 delete_* 等）。
#: 用模式而不是枚举：新增 delete_xxx 时自动纳入，不依赖有人记得改这里。
DIRECT_PATTERNS: tuple[str, ...] = (
    "delete_*",
    "remove_*",
    "destroy_*",
    "clear_all*",
    "reset_and_*",
    "delete_all*",
    "bulk_delete*",
)


def tiers_enabled() -> bool:
    """分层是否启用（默认启用；``off`` 一键回滚到全量直连）。"""
    raw = (os.environ.get(TOOL_TIERS_ENV, "on") or "").strip().lower()
    if raw in ("off", "0", "false", "no"):
        return False
    if raw in ("on", "1", "true", "yes", ""):
        return True
    logger.warning("非法 %s=%r，回退启用分层", TOOL_TIERS_ENV, raw)
    return True


def build_tool_exposure() -> dict[str, str]:
    """生成 pi `mcp.json` 的 ``toolExposure`` 映射。

    返回的键**必须**是 pi 的匹配顺序敏感形式：精确名优先、模式在后。
    pi 的规则是「精确名胜过模式；模式之间先匹配先赢」，所以这里把
    精确清单放在前面，模式放后面（Python dict 保插入序，JSON 序列化保序）。

    返回值直接塞进 ``server["toolExposure"]``；服务端 `exposure` 设为
    ``deferred``（未列出的工具默认走按需加载）。
    """
    mapping: dict[str, str] = {}
    for name in sorted(DIRECT_TOOLS):
        mapping[name] = "direct"
    for pattern in DIRECT_PATTERNS:
        mapping[pattern] = "direct"
    return mapping


def describe_tiers() -> str:
    """给日志用的一句话摘要。"""
    return f"direct={len(DIRECT_TOOLS)} 个精确名 + {len(DIRECT_PATTERNS)} 个破坏性模式，其余走 tool_search 按需加载"
