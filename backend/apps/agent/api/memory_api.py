"""Agent 记忆 API —— 个人记忆管理、策展提升、注入快照。

端点前缀：``/api/v1/agent/memory``

## 为什么快照单独开一个端点

pi 扩展（``pi/memory-inject.ts``）在 ``session_start`` 拉一次快照并缓存，
后续轮次复用同一份字节——这样 system prompt 前缀稳定，prompt cache 能命中。
它需要的是「一个律师的完整记忆块」，不是分页列表，所以不复用
``/agent/memory`` 的列表接口。

## 为什么策展候选与提升分成两个端点

候选池（``GET /promotion/candidates``）是**读**，管理员浏览用；
提升（``POST /promotion``）是**写**，带强制改写与 PII 闸门。
分开是为了让前端能做成「左候选右编辑」的两栏交互，而不是一个模态框里
既拉数据又提交。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router, Schema

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentMemory
from ..services import memory_service

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 记忆"], auth=JWTOrSessionAuth())


def _current_user(request: Any) -> Any:
    user = getattr(request, "auth", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise ValidationException("需要登录")
    return user


def _to_out(memory: AgentMemory) -> dict[str, Any]:
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
    }


class MemoryOut(Schema):
    id: str
    scope: str
    kind: str
    content: str
    status: str
    confidence: float
    hit_count: int
    created_at: str
    source_session_id: str = ""


class MemoryCreateIn(Schema):
    content: str
    kind: str = AgentMemory.Kind.FACT


class MemoryConfirmIn(Schema):
    ids: list[str]
    accept: bool = True


class PromoteCandidateOut(Schema):
    id: str
    kind: str
    content: str
    hit_count: int
    from_lawyer: str = ""
    pii_risk: list[str] = []


class PromoteIn(Schema):
    source_ids: list[str]
    content: str
    kind: str
    scope: str
    team_id: int | None = None


class SnapshotOut(Schema):
    content: str


@router.get("", response=list[MemoryOut])
async def list_memories(  # pragma: no cover
    request: Any,
    scope: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[MemoryOut]:
    """当前律师可见的记忆列表。

    **默认只返回 pending + active**，不返 ``deleted``：软删的语义是「律师不想
    再看到它」，默认列表里还躺着会让人以为删除没生效（前端靠 ``status`` 过滤
    可以遮蔽，但接口本身应该语义正确）。要看已删列表显式传 ``status=deleted``
    （恢复入口需要）。
    """
    lawyer = _current_user(request)

    def _run() -> list[MemoryOut]:
        if status:
            statuses: tuple[str, ...] = (status,)
        else:
            statuses = (AgentMemory.Status.PENDING, AgentMemory.Status.ACTIVE)
        queryset = memory_service.visible_queryset(lawyer, include_status=statuses)
        if scope:
            queryset = queryset.filter(scope=scope)
        bounded = max(1, min(limit, 300))
        return [MemoryOut(**_to_out(m)) for m in queryset[:bounded]]

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("", response=MemoryOut)
async def create_memory(request: Any, payload: MemoryCreateIn) -> MemoryOut:  # pragma: no cover
    """手动新增一条个人记忆（律师主动说「记住…」时的落库端点）。"""
    lawyer = _current_user(request)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.create_memory(
                lawyer,
                content=payload.content,
                kind=payload.kind,
            )
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**_to_out(memory))

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/confirm")
async def confirm_memories(request: Any, payload: MemoryConfirmIn) -> dict[str, Any]:  # pragma: no cover
    """确认或否决待确认（自动抽取/行为推断产出）的记忆。"""
    lawyer = _current_user(request)

    def _run() -> dict[str, Any]:
        count = memory_service.confirm_memories(lawyer, payload.ids, accept=payload.accept)
        return {"ok": True, "affected": count}

    return await sync_to_async(_run, thread_sensitive=True)()


@router.get("/snapshot", response=SnapshotOut)
async def get_snapshot(request: Any, refresh: bool = False) -> SnapshotOut:  # pragma: no cover
    """注入用记忆快照（pi 扩展在 session_start 调用）。

    ``refresh=true`` 仅在长期记忆刚写入时使用——它会让快照内容变化，
    进而破坏该会话后续轮次的 prompt cache 前缀。
    """
    lawyer = _current_user(request)

    def _run() -> SnapshotOut:
        content = memory_service.build_snapshot(lawyer, refresh=refresh, refresh_reason="api")
        return SnapshotOut(content=content)

    return await sync_to_async(_run, thread_sensitive=True)()


@router.get("/promotion/candidates", response=list[PromoteCandidateOut])
async def promotion_candidates(  # pragma: no cover
    request: Any,
    scope: str = AgentMemory.Scope.TEAM,
    team_id: int | None = None,
    limit: int = 50,
) -> list[PromoteCandidateOut]:
    """策展候选池：本团队/本律所成员的个人记忆，按共识度排序。"""
    lawyer = _current_user(request)

    def _run() -> list[PromoteCandidateOut]:
        try:
            rows = memory_service.promote_candidates(lawyer, scope=scope, team_id=team_id, limit=limit)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return [PromoteCandidateOut(**row) for row in rows]

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/promotion", response=MemoryOut)
async def promote_memory(request: Any, payload: PromoteIn) -> MemoryOut:  # pragma: no cover
    """把个人记忆策展提升为团队/律所记忆。

    拒绝原样提升（必须改写）且拒绝含敏感信息的内容，两道闸门都在
    ``memory_service.promote_memory``。
    """
    lawyer = _current_user(request)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.promote_memory(
                lawyer,
                source_ids=payload.source_ids,
                content=payload.content,
                kind=payload.kind,
                scope=payload.scope,
                team_id=payload.team_id,
            )
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**_to_out(memory))

    return await sync_to_async(_run, thread_sensitive=True)()


@router.get("/scopes")
async def my_scopes(request: Any) -> dict[str, Any]:  # pragma: no cover
    """当前律师可策展的作用域（前端据此显示/隐藏「提升到团队」入口）。"""
    lawyer = _current_user(request)

    def _run() -> dict[str, Any]:
        teams = [
            {
                "id": team.pk,
                "name": team.name,
                "can_curate": memory_service.can_curate_scope(lawyer, AgentMemory.Scope.TEAM, team_id=team.pk),
            }
            for team in lawyer.lawyer_teams.all()
        ]
        return {
            "law_firm": {
                "id": lawyer.law_firm_id,
                "can_curate": memory_service.can_curate_scope(lawyer, AgentMemory.Scope.LAW_FIRM),
            },
            "teams": teams,
        }

    return await sync_to_async(_run, thread_sensitive=True)()


# ── 动态段路由（必须放最后）─────────────────────────────────────────────
#
# Django 的路径解析是**按注册顺序匹配**，``/{memory_id}`` 会吞掉任何单段路径。
# 实测踩过：``GET /agent/memory/snapshot`` 命中 ``DELETE /{memory_id}`` 的
# 路径规则，返回 405 Method Not Allowed（allow: DELETE）——注入扩展拿不到
# 快照，记忆功能整体失效且前端无感。所以静态路由必须全部登记在这些之前，
# 新增静态端点时也请往上加，不要写在本段后面。


@router.delete("/{memory_id}")
async def forget_memory(request: Any, memory_id: str) -> dict[str, Any]:  # pragma: no cover
    """软删除一条记忆（可由 ``/{memory_id}/restore`` 恢复）。"""
    lawyer = _current_user(request)

    def _run() -> dict[str, Any]:
        try:
            memory_service.forget_memory(lawyer, memory_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return {"ok": True}

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/{memory_id}/restore", response=MemoryOut)
async def restore_memory(request: Any, memory_id: str) -> MemoryOut:  # pragma: no cover
    """恢复已删除的记忆。"""
    lawyer = _current_user(request)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.restore_memory(lawyer, memory_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return MemoryOut(**_to_out(memory))

    return await sync_to_async(_run, thread_sensitive=True)()
