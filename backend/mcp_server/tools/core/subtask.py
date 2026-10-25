"""派子 agent 做只读调研 —— ``dispatch_research``。

## 什么时候该派子 agent

律师问「这个案子有哪些类似判例」「帮我对比这三份合同的差异」时，如果主 agent
自己去查，`list_*` / `fetch_url` / 附件解析的**全量返回会直接吃掉上下文**——
而这些原始材料 99% 是用完即弃的中间产物。

派一个只读子 agent 去跑，主 agent **只收一行结论 + 关键依据**。

## 什么时候不该派

- **结果很小**（一两条例行查询）：子任务的调度开销比收益大，直接查。
- **需要写操作**（建档案、改金额、发文书）：子 agent 只有只读权限，
  派了也做不了。写操作必须主会话走审批。
- **需要律师即时拍板**：子 agent 不能向律师提问（问也答不到），
  这类分支留在主会话。

## 与审批的关系

子 agent 进程的工具面被收窄成只读白名单（`get_/list_/search_/read_/preview_`），
**结构性地没有写能力**。所以它不可能绕过审批——不是靠策略劝阻，是靠
那些工具压根不在它的进程里。
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_server.identity import current_session_id

#: 默认等待上限（秒）。与 subtask.SUBTASK_WAIT_TIMEOUT 保持一致。
MAX_WAIT_SECONDS = 300


async def dispatch_research(prompt: str, wait_seconds: int = MAX_WAIT_SECONDS) -> dict[str, Any]:
    """派一个只读子 agent 去查资料，等它返回结论。

    **用途**：把「会吃爆上下文的长查询」外包给子 agent。典型场景——查类案、
    比对多份合同、读多份材料后汇总。子 agent 只能读不能写。

    **不要用于**：

    - 一两条就能查完的小查询（直接调 `list_*` / `get_*` 更快）；
    - 任何需要写入的操作（子 agent 没有写权限，派了也做不了）；
    - 需要律师当场决定的分支（子 agent 问不到律师）。

    Args:
        prompt: 交给子 agent 的任务说明。要写清：**查什么**、**要回答什么**、
            **依据怎么给**（例如「列出案号 + 法院 + 裁判日期，每条一句话说明
            与本案的相似点」）。写得越具体，回来的结论越可用。
        wait_seconds: 等待上限，默认 300 秒。超时会返回部分结果并提示——
            此时**不要**假装拿到了完整结论。

    Returns:
        - ``status="succeeded"``：``result`` 是子 agent 的最终答复原文；
          ``tokens`` / ``duration_ms`` 是这次调研的成本。
        - ``status="failed"``：``error`` 说明原因，``hint`` 给出下一步建议。
        - ``status="timeout"``：超时，通常需要拆成更小的子任务重派。

        **无论哪种状态，都要如实告诉律师「这项检索成没成」**，不能把
        `failed` / `timeout` 含糊成「没有找到相关判例」——后者会被误读成
        「检索过了，确实没有」，那是完全不同的事实。
    """
    from apps.agent.models import AgentSession
    from apps.agent.services import subtask as subtask_service

    session_id = current_session_id()
    if not session_id:
        return {
            "status": "failed",
            "error": "当前没有会话上下文，无法派子任务",
            "hint": "请直接自己查询（不要编造结论）。",
        }

    parent = await AgentSession.objects.filter(session_id=session_id).afirst()
    if parent is None:
        return {
            "status": "failed",
            "error": "找不到当前会话，无法派子任务",
            "hint": "请直接自己查询。",
        }

    try:
        record = await subtask_service.dispatch(
            parent_session=parent,
            prompt=prompt,
            user_id=parent.user_id,
        )
    except ValueError as exc:
        # 并发超限 / prompt 不合法：都是「换个做法」而不是「系统坏了」
        return {
            "status": "failed",
            "error": str(exc),
            "hint": "按提示调整后重派，或直接自己查询这一项。",
        }

    effective_wait = min(max(int(wait_seconds), 30), MAX_WAIT_SECONDS)
    result = await subtask_service.wait_for_result(record.subtask_id, timeout=float(effective_wait))
    result["subtask_id"] = str(record.subtask_id)
    result["readonly_note"] = subtask_service.readonly_prefixes_doc()
    return result
