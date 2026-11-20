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


#: 项目笔记单条字数上限。比普通记忆（200）宽一点：一句判断得带上理由；
#: 但硬性卡在 300——渲染时**不截断**，截断的判断比没有判断更危险。
NOTE_MAX_CHARS = 300


def _require_anchor(*, contract_id: int | None, case_id: int | None) -> None:
    if contract_id is None and case_id is None:
        raise ValueError("项目笔记必须挂到项目（contract_id）或案件（case_id）上")


def _contract_of_case(case_id: int | None) -> int | None:
    """只给案件时补上项目锚点。

    为什么必须补：项目页「AI 上下文」面板按 ``contract_id`` 查，而
    ``anchor_q`` 生成的是 ``Q(contract_id=X)``——**``contract_id IS NULL`` 的行
    永远不匹配**。不补的话，模型用 ``save_case_note`` 只给 case_id 存下的判断，
    在案件会话里能注入、在项目页却看不见（真机验证过）。

    推导与建会话共用 ``session_service.contract_id_for_case``：同一个「案件属于
    哪个项目」只能有一个答案。``Case.contract`` 允许为空，查不到就保持 None。
    """
    from ..session_service import contract_id_for_case

    return contract_id_for_case(case_id)


def _editable_note(lawyer: Lawyer, memory_id: str) -> AgentMemory:
    """取一条「我能动」的项目笔记。

    能动 = 挂了锚点 + 作者在**同一律师团队**里（与注入侧同一个可见性口径：
    项目就是权限泡，团队成员等价）。团队外的人拿到 id 也改不了。
    """
    note = (
        AgentMemory.objects.filter(
            pk=memory_id, status=AgentMemory.Status.ACTIVE, lawyer_id__in=list(scopes.team_member_ids(lawyer))
        )
        .exclude(contract_id__isnull=True, case_id__isnull=True)
        .first()
    )
    if note is None:
        raise ValueError("笔记不存在或无权访问")
    return note


def create_note(
    lawyer: Lawyer,
    *,
    content: str,
    contract_id: int | None = None,
    case_id: int | None = None,
    kind: str = AgentMemory.Kind.FACT,
    source_session: AgentSession | None = None,
    supersede_id: str | None = None,
) -> AgentMemory:
    """写一条**项目笔记**（附在项目/案件上的判断）。

    ## 为什么独立于 ``create_memory``

    两者是两种东西：``create_memory`` 存的是「这个律师/团队的习惯」，跨项目
    通用、按 scope 分层；本函数存的是「这个项目的结论」，只在本项目/本案的
    会话里说得上话。把它们搅在一起（比如给 scope 再加一个 project 档）会让
    可见性出现两套语义——一套是团队，一套是项目，迟早漂移。

    ## 三条行为约定

    1. **谁都能写**：被指派到该项目的律师都能写（律师团队即可见集），
       不设审核闸——只靠 author/时间/被谁推翻 可追溯；
    2. **立刻生效**：写入即 ``status=active``（不跟自动抽取的 pending 混）。
       不生效的话「存进项目笔记」按了等于没按；
    3. **不静默覆盖**：同一句内容重复写只会提升置信度；要推翻旧结论就传
       ``supersede_id``——旧条留在库里（不删除），只是不再注入。
    """
    _require_anchor(contract_id=contract_id, case_id=case_id)
    if contract_id is None:
        contract_id = _contract_of_case(case_id)
    raw = (content or "").strip()
    if not raw:
        raise ValueError("笔记内容不能为空")
    if len(raw) > NOTE_MAX_CHARS:
        raise ValueError(f"笔记过长（上限 {NOTE_MAX_CHARS} 字），请拆成几条")
    if kind not in AgentMemory.Kind.values:
        raise ValueError(f"未知的记忆类型: {kind}")
    normalized = " ".join(raw.split())

    with transaction.atomic():
        note, created = AgentMemory.objects.get_or_create(
            scope=AgentMemory.Scope.LAWYER,
            lawyer=lawyer,
            content_hash=content_hash_of(normalized),
            status__in=[AgentMemory.Status.PENDING, AgentMemory.Status.ACTIVE],
            defaults={
                "kind": kind,
                "content": normalized,
                "status": AgentMemory.Status.ACTIVE,
                "confidence": 1.0,
                "source_session": source_session,
                "created_by": lawyer,
                "contract_id": contract_id,
                "case_id": case_id,
            },
        )
        if not created:
            # 同一内容重复写入：提升置信度；并在旧行没锚点时补上锚点（不改内容）
            updates = ["confidence", "updated_at"]
            note.confidence = max(note.confidence, 1.0)
            if note.contract_id is None and contract_id is not None:
                note.contract_id = contract_id
                updates.append("contract_id")
            if note.case_id is None and case_id is not None:
                note.case_id = case_id
                updates.append("case_id")
            note.save(update_fields=updates)

        if supersede_id:
            old = _editable_note(lawyer, supersede_id)
            note.supersedes = old
            note.save(update_fields=["supersedes"])

    _ensure_embedding(note)
    snapshot.invalidate_snapshot(lawyer)
    return note


def confirm_note(lawyer: Lawyer, memory_id: str, *, content: str | None = None) -> AgentMemory:
    """把一条项目笔记升为**项目事实**（人工点一下）。

    为什么必须手动：模型写的判断本身不可靠（可能是它自己的推理，也可能是
    被卷宗里的文字带偏的）。一旦标成「事实」，后面的会话会当成前提交用，
    错误会被不断放大。所以升级动作只能由人发出，且可带一次改写（律师说得
    更准），改写时同步重算指纹。
    """
    note = _editable_note(lawyer, memory_id)

    updates: list[str] = ["confirmed_at", "confirmed_by", "updated_at"]
    if content is not None:
        raw = content.strip()
        if not raw:
            raise ValueError("笔记内容不能为空")
        if len(raw) > NOTE_MAX_CHARS:
            raise ValueError(f"笔记过长（上限 {NOTE_MAX_CHARS} 字）")
        note.content = " ".join(raw.split())
        note.content_hash = content_hash_of(note.content)
        updates.extend(["content", "content_hash"])

    note.confirmed_at = timezone.now()
    note.confirmed_by = lawyer
    note.save(update_fields=updates)
    snapshot.invalidate_snapshot(lawyer)
    return note


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
