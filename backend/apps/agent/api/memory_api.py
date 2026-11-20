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

读侧的过滤/截断/作用域装配等业务逻辑下沉在 ``services/memory/payloads.py``，
本层只把 service 载荷装进 Ninja Schema。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from ninja import Router

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentMemory, AgentSession
from ..schemas import (
    MemoryConfirmIn,
    MemoryCreateIn,
    MemoryHitOut,
    MemoryOut,
    NoteConfirmIn,
    ProjectNoteIn,
    PromoteCandidateOut,
    PromoteIn,
    SnapshotOut,
)
from ..services import memory_service

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 记忆"], auth=JWTOrSessionAuth())


def _current_user(request: Any) -> Any:
    user = getattr(request, "auth", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise ValidationException("需要登录")
    return user


@router.get("", response=list[MemoryOut])
async def list_memories(  # pragma: no cover
    request: Any,
    scope: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    contract_id: int | None = None,
    case_id: int | None = None,
) -> list[MemoryOut]:
    """当前律师可见的记忆列表（默认 pending + active，业务逻辑见 service）。

    ``contract_id`` / ``case_id``：只看挂在某个项目/案件上的项目笔记，
    供「项目页 AI 上下文面板」使用。两个都给时取并集（与注入侧同一语义）。
    ``offset`` 配合 ``limit`` 翻页（面板的「加载更多」）。
    """
    lawyer = _current_user(request)
    rows = await sync_to_async(memory_service.list_memories_payload, thread_sensitive=True)(
        lawyer,
        scope=scope,
        status=status,
        limit=limit,
        offset=offset,
        contract_id=contract_id,
        case_id=case_id,
    )
    return [MemoryOut(**row) for row in rows]


@router.post("", response=MemoryOut)
async def create_memory(request: Any, payload: MemoryCreateIn) -> MemoryOut:  # pragma: no cover
    """手动新增一条个人记忆（律师主动说「记住…」时的落库端点）。"""
    lawyer = _current_user(request)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.create_memory(lawyer, content=payload.content, kind=payload.kind)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**memory_service.memory_to_dict(memory))

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/confirm")
async def confirm_memories(request: Any, payload: MemoryConfirmIn) -> dict[str, Any]:  # pragma: no cover
    """确认或否决待确认（自动抽取/行为推断产出）的记忆。"""
    lawyer = _current_user(request)

    def _run() -> dict[str, Any]:
        count = memory_service.confirm_memories(lawyer, payload.ids, accept=payload.accept)
        return {"ok": True, "affected": count}

    return await sync_to_async(_run, thread_sensitive=True)()


@router.get("/search", response=list[MemoryHitOut])
async def search_memory(request: Any, q: str, limit: int = 8) -> list[MemoryHitOut]:  # pragma: no cover
    """语义 + 关键词混合检索（``recall_memory`` MCP 工具的后端）。

    与 ``GET /`` 的区别：``GET /`` 是按时间倒序**浏览**全部记忆（管理界面）；
    ``GET /search`` 是按相关度**检索** top-N（带向量召回）。律师问「我以前
    说的格式要求」时，记忆里存的是「文书先给结论」——字面无关、语义相关，
    列表浏览永远找不到。
    """
    lawyer = _current_user(request)
    query = (q or "").strip()
    if not query:
        raise ValidationException("检索词不能为空")
    rows = await sync_to_async(memory_service.search_memories_payload, thread_sensitive=True)(
        lawyer, query, limit=limit
    )
    return [MemoryHitOut(**row) for row in rows]


async def _session_anchors(*, session_id: str | None, user_id: int) -> tuple[int | None, int | None]:
    """会话 → ``(contract_id, case_id)``，用于把「本项目/本案」的笔记挑出来。

    三条安全约定：

    1. **会话归属必须校验**：只按 ``user_id`` 现查，拿别人的 session_id 也
       只会得到 ``(None, None)``——本项目笔记虽然团队共享，但不能靠猜
       session_id 去探别人正在办哪个案子；
    2. 非法 UUID 一律当作「没有锚点」，不抛 500（扩展是每轮热路径）；
    3. 没有 session_id（旧扩展、纯对话入口）时行为与引入锚点前**完全一致**。
    """
    if not session_id:
        return None, None
    try:
        row = (
            await AgentSession.objects.filter(session_id=session_id, user_id=user_id)
            .values("case_id", "contract_id")
            .afirst()
        )
    except (ValueError, ValidationError):
        return None, None
    if not row:
        return None, None
    return row["contract_id"], row["case_id"]


@router.get("/snapshot", response=SnapshotOut)
async def get_snapshot(
    request: Any, refresh: bool = False, session_id: str | None = None
) -> SnapshotOut:  # pragma: no cover
    """注入用记忆快照（pi 扩展在 session_start 调用）。

    ``refresh=true`` 仅在长期记忆刚写入时使用——它会让快照内容变化，
    进而破坏该会话后续轮次的 prompt cache 前缀。

    ``session_id`` 决定「本项目/本案」那两块要不要渲染：带着它才会把同团队
    写在该项目上的笔记注入进来（跨会话共享判断的唯一入口）。
    """
    lawyer = _current_user(request)
    contract_id, case_id = await _session_anchors(session_id=session_id, user_id=lawyer.pk)

    def _run() -> SnapshotOut:
        content = memory_service.build_snapshot(
            lawyer,
            contract_id=contract_id,
            case_id=case_id,
            refresh=refresh,
            refresh_reason="api",
        )
        return SnapshotOut(content=content)

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/notes", response=MemoryOut)
async def create_project_note(request: Any, payload: ProjectNoteIn) -> MemoryOut:  # pragma: no cover
    """写一条项目笔记（挂到项目或某案件上）。

    与 ``POST /agent/memory`` 的区别：那条存的是**这个律师的习惯**（跨项目
    通用，按 scope 分层）；这条存的是**这个项目的结论**，只在本项目/本案的
    会话里注入，同团队所有人都看得到、都写得了。
    """
    lawyer = _current_user(request)
    contract_id, case_id = payload.contract_id, payload.case_id
    if contract_id is None and case_id is None:
        contract_id, case_id = await _session_anchors(session_id=payload.session_id, user_id=lawyer.pk)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.create_note(
                lawyer,
                content=payload.content,
                contract_id=contract_id,
                case_id=case_id,
                kind=payload.kind,
                supersede_id=payload.supersede_id,
            )
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**memory_service.memory_to_dict(memory))

    return await sync_to_async(_run, thread_sensitive=True)()


@router.post("/{memory_id}/confirm", response=MemoryOut)
async def confirm_project_note(request: Any, memory_id: str, payload: NoteConfirmIn) -> MemoryOut:  # pragma: no cover
    """把一条笔记升为「项目事实」（人工点一下），可顺带改写内容。

    为什么要人点：模型写的判断可能是它自己的推理，也可能被卷宗里的文字带偏。
    一旦标成事实，后面的会话会当**前提**使用，错误会被逐轮放大。
    """
    lawyer = _current_user(request)

    def _run() -> MemoryOut:
        try:
            memory = memory_service.confirm_note(lawyer, memory_id, content=payload.content)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**memory_service.memory_to_dict(memory))

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
                acknowledged_firm_wide=payload.acknowledged_firm_wide,
            )
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return MemoryOut(**memory_service.memory_to_dict(memory))

    return await sync_to_async(_run, thread_sensitive=True)()


@router.get("/scopes")
async def my_scopes(request: Any) -> dict[str, Any]:  # pragma: no cover
    """当前律师可策展的作用域（前端据此显示/隐藏「提升到团队」入口）。"""
    lawyer = _current_user(request)
    return await sync_to_async(memory_service.curatable_scopes_payload, thread_sensitive=True)(lawyer)


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
        return MemoryOut(**memory_service.memory_to_dict(memory))

    return await sync_to_async(_run, thread_sensitive=True)()
