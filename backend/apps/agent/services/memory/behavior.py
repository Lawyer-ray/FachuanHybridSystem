"""行为推断（零 LLM、零幻觉）—— 从既有审计数据推断偏好。

读的是 ``AgentApproval``（谁批了什么）与 ``AgentRun``（工具调用数）。
准确率接近 1，成本为零，且不需要律师做任何事。这是 pi-memory 那类
「靠用户说记住」方案做不到的一块。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Avg

from ...models import AgentApproval, AgentMemory, AgentRun
from . import write

if TYPE_CHECKING:
    from apps.organization.models import Lawyer


def derive_preferences_from_behavior(lawyer: Lawyer) -> list[dict[str, Any]]:
    """从既有审计数据推断偏好，产出**待确认**记忆。

    这条路径不调 LLM——它读的是 ``AgentApproval``（谁批了什么）与
    ``AgentRun``（工具调用数）。准确率接近 1，成本为零，且不需要律师做任何事。
    这是 pi-memory 那类「靠用户说记住」方案做不到的一块。
    """
    suggestions: list[dict[str, Any]] = []

    # 1) 审批模式：对同一类高危工具连续拒绝 → 建议默认拒绝
    rejections: dict[str, int] = {}
    approvals: dict[str, int] = {}
    for tool_name, status in AgentApproval.objects.filter(decided_by=lawyer).values_list("tool_name", "status")[:2000]:
        if status == "rejected":
            rejections[tool_name] = rejections.get(tool_name, 0) + 1
        elif status == "approved":
            approvals[tool_name] = approvals.get(tool_name, 0) + 1

    for tool_name, count in rejections.items():
        if count >= 3 and approvals.get(tool_name, 0) == 0:
            suggestions.append(
                {
                    "content": f"对 {tool_name} 一律拒绝，除非明确要求（历史上 {count} 次调用全部被拒绝）",
                    "kind": AgentMemory.Kind.PREFERENCE,
                    "confidence": 0.9,
                    "evidence": "approval_history",
                }
            )

    # 2) 使用强度：高频使用说明依赖度高，值得记一条以提示优先走该路径
    runs = AgentRun.objects.filter(user=lawyer, status="ok").count()
    if runs >= 50:
        aggregated = AgentRun.objects.filter(user=lawyer, status="ok").aggregate(avg_calls=Avg("tool_calls"))
        avg_calls = aggregated.get("avg_calls")
        if avg_calls and float(avg_calls) >= 4:
            suggestions.append(
                {
                    "content": f"习惯让助手多轮并行取证（平均每次会话调用 {float(avg_calls):.1f} 个工具），可优先直接给出完整结果而非逐步确认",
                    "kind": AgentMemory.Kind.PREFERENCE,
                    "confidence": 0.8,
                    "evidence": "run_stats",
                }
            )

    return suggestions


def persist_suggestions(lawyer: Lawyer, suggestions: list[dict[str, Any]]) -> int:
    """把行为推断的建议落为 pending 记忆（同样需要律师确认）。"""
    count = 0
    for item in suggestions:
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        try:
            write.create_memory(
                lawyer,
                content=content,
                kind=str(item.get("kind") or AgentMemory.Kind.PREFERENCE),
                status=AgentMemory.Status.PENDING,
                confidence=float(item.get("confidence", 0.8)),
            )
            count += 1
        except ValueError:
            continue
    return count
