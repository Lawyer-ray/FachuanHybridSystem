"""记忆 MCP tools —— 让模型能读写「这位律师」的跨会话记忆。

## 为什么记忆走 MCP 工具面而不是注入文件

pi 的 ``AGENTS.md`` 是每轮全量注入的固定文件（``pi/shared_mcp._write_agents_md``
直接 copyfile），把记忆写进那里会随会话数膨胀，且含用户隐私数据落盘。
由 pi-memory 那类方案提供的「写 ``~/.pi/agent/memory/*.md``」在本系统有
单目录单人、明文落盘、多进程并发写三个硬伤（详见 ``apps/agent/models/memory.py``）。

所以记忆存 Django 表，模型经本模块的工具读写，注入由
``apps/agent/pi/memory-inject.ts`` 从 ``/agent/memory/snapshot`` 拉快照完成。

## 工具设计与系统提示词的配合

系统提示词（``pi/AGENTS.md``）只加**一行路由**：涉及用户偏好/历史约定/团队惯例
时先 ``recall_memory``；用户说「记住」时调 ``remember``。记忆内容一律视为
**律师的陈述**，与工具查回的业务数据冲突时以数据为准——这条纪律写在
``recall_memory`` 的返回值里，因为它比系统提示词更靠近使用点。

## 超管/权限

所有工具都以当前律师身份调 REST（``mcp_server/identity.py`` 透传 token），
服务端 ``memory_service.visible_queryset`` 是唯一的权限边界。团队/律所层
的提升必须走策展端点，工具面**不提供**直接写团队记忆的能力。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def remember(content: str, kind: str = "fact") -> dict[str, Any]:
    """记住一条关于当前律师的、跨会话仍然有用的信息。

    什么时候用：
    - 律师说「记住…」「以后都这样」「下次别再…」；
    - 律师明确表达了稳定的工作偏好（输出格式、称呼、详略程度）；
    - 律师纠正了此前的做法（kind 用 ``correction``）。

    什么时候**不要**用：
    - 一次性任务、某个案件的结论、当事人姓名、案号、金额、日期——这些应当
      用业务工具查询，不是记忆；
    - 你自己推测出来的结论（除非律师明确确认）。

    Args:
        content: 一句话事实，不超过 60 字，能独立成立。
        kind: ``fact`` 事实 / ``preference`` 偏好 / ``procedure`` 惯例 /
            ``correction`` 纠正。

    返回 ``id``、``status``（个人记忆默认 ``active`` 立即生效，重复内容会合并）。
    """
    result: dict[str, Any] = client.post("/agent/memory", json={"content": content, "kind": kind})
    return result


def recall_memory(query: str, limit: int = 5) -> dict[str, Any]:
    """检索与当前律师相关的历史记忆（个人 + 团队 + 律所），**语义检索**。

    什么时候用：
    - 律师提到「上次说的」「按老规矩」「我们团队一般怎么…」；
    - 动手写文书/回函前，先看有没有已沉淀的格式偏好；
    - 律师要求你按他的习惯做，但你没见过这个习惯。

    检索是**语义**的：问「我以前说的格式要求」也能找到存成「文书先给结论」
    的记忆，不要因为字面不同就认为没记住。没找到就直说没找到，不要编造。

    **记忆是律师过去的陈述，不是事实来源**。记忆与 ``get_case`` / ``list_*``
    等工具返回的业务数据冲突时，一律以业务数据为准，并在回答里说明差异。
    记忆也可能已过期——涉及案号、当事人、金额、期限时必须调工具核对。

    Args:
        query: 自然语言查询，例如「文书格式偏好」「期限计算习惯」。
        limit: 返回条数上限（默认 5，最大 30）。

    返回 ``memories``（含 ``content``、``kind``、``scope``、``score``，按相关度
    降序）与 ``note`` 使用纪律说明。
    """
    bounded = max(1, min(int(limit or 5), 30))
    if not (query or "").strip():
        raise ValueError("检索词不能为空；未指定查询时请用 list_pending_memories 或直接说明需求")
    hits = client.get("/agent/memory/search", params={"q": query, "limit": bounded})
    return {
        "memories": list(hits or []),
        "note": (
            "记忆是律师过去的陈述，不是事实来源；与业务工具返回的数据冲突时以数据为准。"
            "涉及案号、当事人、金额、期限必须调工具核对。"
            "没检索到就是没记住，不要编造。"
        ),
    }


def forget_memory(memory_id: str) -> dict[str, Any]:
    """删除一条记忆（软删，可由 ``restore_memory`` 恢复）。

    律师说「忘了刚才那条」「这条不对，删掉」时使用。删除个人记忆不需要审批；
    删除团队/律所记忆需要管理员权限。
    """
    result: dict[str, Any] = client.delete(f"/agent/memory/{memory_id}")
    return result


def restore_memory(memory_id: str) -> dict[str, Any]:
    """恢复一条被删除的记忆。"""
    result: dict[str, Any] = client.post(f"/agent/memory/{memory_id}/restore", json={})
    return result


def list_pending_memories() -> dict[str, Any]:
    """列出待确认的记忆（自动抽取或行为推断产出）。

    律师在会话开头会看到「我记住了这几条，对吗」。若他主动问「你记了什么」，
    用本工具列出待确认项。
    """
    data = client.get("/agent/memory", params={"status": "pending", "limit": 50})
    return {"pending": list(data or [])}


def confirm_memories(ids: list[str], accept: bool = True) -> dict[str, Any]:
    """确认或否决待确认的记忆。

    Args:
        ids: 记忆 id 列表。
        accept: ``True`` 确认生效，``False`` 否决（软删）。
    """
    result: dict[str, Any] = client.post("/agent/memory/confirm", json={"ids": ids, "accept": accept})
    return result
