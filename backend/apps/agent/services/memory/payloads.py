"""记忆 API 的读侧载荷装配（业务逻辑下沉层）。

API 层只负责把这里的 dict 载荷装进 Ninja Schema；过滤、截断、作用域装配
等业务逻辑都在 service 侧，避免四层架构里「API 做业务」的违规。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Exists, OuterRef

from ...models import AgentMemory
from .scopes import anchor_q, can_curate_scope, visible_queryset
from .search import search_memories

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

#: 检索返回的单条内容上限（字）。操作指引上限 8000，留足不截断；
#: 真正超出的会带 truncated=True，由模型决定是否收窄查询。
SEARCH_CONTENT_MAX_CHARS = 8000


def memory_to_dict(memory: AgentMemory) -> dict[str, Any]:
    """单条记忆 → 对外 dict（MemoryOut 的字段来源）。"""
    return {
        "id": str(memory.pk),
        "scope": memory.scope,
        "kind": memory.kind,
        "content": memory.content,
        "status": memory.status,
        "confidence": memory.confidence,
        "hit_count": memory.hit_count,
        "created_at": memory.created_at.isoformat() if memory.created_at else "",
        "source_session_id": (str(memory.source_session.session_id) if memory.source_session is not None else ""),
        # 项目锚点：前端靠它们把笔记归到「项目/本案」，也靠 confirmed_at 区分
        # 「同事的判断」与「已确认的项目事实」。
        "contract_id": memory.contract_id,
        "case_id": memory.case_id,
        "confirmed_at": memory.confirmed_at.isoformat() if memory.confirmed_at else "",
        "confirmed_by": (str(memory.confirmed_by) if memory.confirmed_by_id else ""),
        "supersedes_id": str(memory.supersedes_id) if memory.supersedes_id else "",
        # 是否已被后来的条目标为「推翻」。注入侧靠 superseded_by__isnull 过滤，
        # 但**列表/面板要看到它并标出来**：否则抽屉里会并排显示两条互相矛盾的
        # 结论、还没有任何提示，律师按旧结论办事的风险比看不到更高。
        "is_superseded": bool(getattr(memory, "is_superseded", False)),
    }


def list_memories_payload(
    lawyer: Lawyer,
    *,
    scope: str | None,
    status: str | None,
    limit: int,
    contract_id: int | None = None,
    case_id: int | None = None,
) -> list[dict[str, Any]]:
    """当前律师可见的记忆列表载荷。

    默认只返回 pending + active（软删的语义是「不想再看到」）；显式传
    ``status`` 则按该状态过滤（恢复入口需要 ``status=deleted``）。

    ``contract_id`` / ``case_id`` 用于「项目页的 AI 上下文面板」：只取挂在
    本项目/本案上的笔记（两个都给时取并集，与注入侧 ``anchor_q`` 同一语义，
    避免「面板看到 5 条、注入只有 3 条」这种两套口径）。
    """
    if status:
        statuses: tuple[str, ...] = (status,)
    else:
        statuses = (AgentMemory.Status.PENDING, AgentMemory.Status.ACTIVE)
    queryset = visible_queryset(lawyer, include_status=statuses)
    if scope:
        queryset = queryset.filter(scope=scope)
    anchor = anchor_q(contract_id=contract_id, case_id=case_id)
    if anchor is not None:
        queryset = queryset.filter(anchor)
    # 一条被谁推翻 = 存在另一条把 supersedes 指向它（注解而不是逐行查，避免 N+1）
    queryset = queryset.annotate(is_superseded=Exists(AgentMemory.objects.filter(supersedes=OuterRef("pk"))))
    bounded = max(1, min(limit, 300))
    return [memory_to_dict(m) for m in queryset[:bounded]]


def search_memories_payload(lawyer: Lawyer, query: str, *, limit: int) -> list[dict[str, Any]]:
    """混合检索载荷：按相关度 top-N，内容超限截断并标 truncated。"""
    bounded = max(1, min(limit, 30))
    hits = search_memories(lawyer, query, limit=bounded)
    out: list[dict[str, Any]] = []
    for memory, score in hits:
        content = memory.content or ""
        clipped = len(content) > SEARCH_CONTENT_MAX_CHARS
        out.append(
            {
                "id": str(memory.pk),
                "scope": memory.scope,
                "kind": memory.kind,
                # 操作指引按需取全文，这里给足；普通记忆本来就短
                "content": content[:SEARCH_CONTENT_MAX_CHARS],
                "score": round(float(score), 4),
                "truncated": clipped,
            }
        )
    return out


def curatable_scopes_payload(lawyer: Lawyer) -> dict[str, Any]:
    """当前律师可策展的作用域载荷（前端据此显示/隐藏「提升到团队」入口）。"""
    teams = [
        {
            "id": team.pk,
            "name": team.name,
            "can_curate": can_curate_scope(lawyer, AgentMemory.Scope.TEAM, team_id=team.pk),
        }
        for team in lawyer.lawyer_teams.all()
    ]
    return {
        "law_firm": {
            "id": lawyer.law_firm_id,
            "can_curate": can_curate_scope(lawyer, AgentMemory.Scope.LAW_FIRM),
        },
        "teams": teams,
    }
