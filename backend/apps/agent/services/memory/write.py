"""记忆写入 —— 创建、确认、软删与恢复。

个人层默认 ``active``（律师自己说的，立刻生效）；团队/律所层**必须**走
``curation.promote_memory()``，这里直接拒绝，防止有人绕过策展闸门。

``content_hash`` 一律在写入口经 ``content_hash_of`` 派生（Model 不做业务
计算）：去重约束与「同一事实被反复抽取」的幂等都锚定在这个指纹上。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from ...models import AgentMemory, AgentSession, content_hash_of
from . import scopes, search, snapshot

if TYPE_CHECKING:
    from apps.organization.models import Lawyer


def create_memory(
    lawyer: Lawyer,
    *,
    content: str,
    kind: str = AgentMemory.Kind.FACT,
    scope: str = AgentMemory.Scope.LAWYER,
    status: str | None = None,
    source_session: AgentSession | None = None,
    confidence: float = 1.0,
) -> AgentMemory:
    """创建一条记忆。

    个人层默认 ``active``（律师自己说的，立刻生效）；团队/律所层**必须**走
    ``promote_memory()``，这里直接拒绝，防止有人绕过策展闸门。
    """
    # 保留换行：操作指引是多行结构（步骤/要点），压成一行会丢失组织。
    # 其余类型压平——它们应当是一句可复用的事实。
    raw = (content or "").strip()
    if not raw:
        raise ValueError("记忆内容不能为空")
    content = raw if kind == AgentMemory.Kind.PLAYBOOK else " ".join(raw.split())
    limit = snapshot.PLAYBOOK_MAX_CHARS if kind == AgentMemory.Kind.PLAYBOOK else snapshot.MAX_SINGLE_ENTRY_CHARS * 5
    if len(content) > limit:
        raise ValueError(
            f"记忆内容过长（上限 {limit} 字）{'，请拆分' if kind == AgentMemory.Kind.PLAYBOOK else '，请提炼成一句可复用的事实'}"
        )
    if scope != AgentMemory.Scope.LAWYER:
        raise ValueError("团队/律所记忆只能通过策展提升创建，不能直接写入")
    if kind not in AgentMemory.Kind.values:
        raise ValueError(f"未知的记忆类型: {kind}")

    if status is None:
        status = AgentMemory.Status.ACTIVE

    with transaction.atomic():
        memory, created = AgentMemory.objects.get_or_create(
            scope=AgentMemory.Scope.LAWYER,
            lawyer=lawyer,
            content_hash=content_hash_of(content),
            status__in=[AgentMemory.Status.PENDING, AgentMemory.Status.ACTIVE],
            defaults={
                "kind": kind,
                "content": content,
                "status": status,
                "confidence": confidence,
                "source_session": source_session,
                "created_by": lawyer,
            },
        )
        if not created:
            # 同一内容重复写入：提升置信度而不是新增行
            memory.confidence = max(memory.confidence, confidence)
            if status == AgentMemory.Status.ACTIVE and memory.status == AgentMemory.Status.PENDING:
                memory.status = AgentMemory.Status.ACTIVE
            memory.save(update_fields=["confidence", "status", "updated_at"])
    _ensure_embedding(memory)
    snapshot.invalidate_snapshot(lawyer)
    return memory


def _ensure_embedding(memory: AgentMemory) -> None:
    """补向量。失败不影响主流程（检索会退化为关键词）。"""
    if memory.embedding:
        return
    vector = search._embed_query(memory.content)
    if not vector:
        return
    AgentMemory.objects.filter(pk=memory.pk).update(embedding=vector)


def confirm_memories(lawyer: Lawyer, memory_ids: list[str], *, accept: bool) -> int:
    """确认/否决待确认记忆（律师在会话开头看到「我记住了这几条，对吗」）。

    返回实际处理的条数。
    """
    if not memory_ids:
        return 0
    qs = AgentMemory.objects.filter(
        pk__in=memory_ids, scope=AgentMemory.Scope.LAWYER, lawyer=lawyer, status=AgentMemory.Status.PENDING
    )
    target = AgentMemory.Status.ACTIVE if accept else AgentMemory.Status.DELETED
    count = qs.update(status=target, updated_at=timezone.now())
    snapshot.invalidate_snapshot(lawyer)
    return count


def forget_memory(lawyer: Lawyer, memory_id: str) -> None:
    """软删。保留行以支持 ``restore_memory``（借 pi-memory 的 forget/restore）。"""
    memory = (
        scopes.visible_queryset(lawyer, include_status=tuple(AgentMemory.Status.values)).filter(pk=memory_id).first()
    )
    if memory is None:
        raise ValueError("记忆不存在或无权访问")
    if memory.scope != AgentMemory.Scope.LAWYER and not scopes._can_curate(lawyer, memory):
        raise ValueError("只有管理员可以删除团队/律所记忆")
    memory.status = AgentMemory.Status.DELETED
    memory.save(update_fields=["status", "updated_at"])
    snapshot.invalidate_snapshot(lawyer)


def restore_memory(lawyer: Lawyer, memory_id: str) -> AgentMemory:
    """恢复已删除的记忆。"""
    memory = scopes.visible_queryset(lawyer, include_status=(AgentMemory.Status.DELETED,)).filter(pk=memory_id).first()
    if memory is None:
        raise ValueError("找不到可恢复的记忆")
    memory.status = AgentMemory.Status.ACTIVE
    memory.save(update_fields=["status", "updated_at"])
    snapshot.invalidate_snapshot(lawyer)
    return memory
