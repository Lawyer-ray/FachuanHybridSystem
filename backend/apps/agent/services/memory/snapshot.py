"""注入快照 —— 渲染、缓存与失效。

记忆块若每轮重算并拼进 system prompt，前缀每轮都变，**prompt cache 全废**。
所以渲染出的快照按会话缓存，只在 pi 扩展的 ``session_start`` /
``session_before_compact`` / 长期记忆写入 / 跨天时失效。

缓存落 Django cache（Redis 或 locmem），不用进程内变量：``pool.acquire()``
每请求起一个新 pi 进程，进程内变量根本跨不了轮次。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.apps import apps as django_apps
from django.core.cache import cache

from ...models import AgentMemory
from . import scopes, search

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

# ── 配额 ────────────────────────────────────────────────────────────────
#: 每层每轮注入的字数上限。参考 pi-memory 的 16K 总上限，但我们严得多：
#: 法律场景下每层塞满长文反而稀释指令。1600/900/700 合计 3200 字，
#: 约 2000-2500 token，对 200K 上下文是可接受的固定开销。
INJECT_QUOTA_LAWYER = 1600
INJECT_QUOTA_TEAM = 900
INJECT_QUOTA_LAW_FIRM = 700

#: 项目层（合同）**已确认事实**的字数上限。
#:
#: 为什么单独开一块而不是从上面三层里切：项目事实是「本案怎么打」的前提，
#: 一旦被个人偏好挤掉，后面每一轮都在错误前提上推理；反过来把个人层削小
#: 又会让「先结结论再给理由」这类硬偏好失效。两块各算各的额度。
INJECT_QUOTA_PROJECT_FACT = 1200

#: 项目层**判断**（同事会话得出的、未经人确认的结论）的字数上限。
#: 比事实块小：判断可被推翻，且必须能与事实一眼区分，否则模型会把推测
#: 当既成事实继续往下推。
INJECT_QUOTA_PROJECT_JUDGMENT = 800

#: 单条记忆的字数上限。超过说明抽取失败（把整段对话当记忆了），
#: 该类条目不参与注入，但仍留在库里供人处理。
MAX_SINGLE_ENTRY_CHARS = 200

#: 操作指引索引区额外额度（字）。短规则配额已满时，仍要让「本所还有 3 份
#: 操作指引」这行可见——看不到索引就永远不会去取全文，通道等于不存在。
INDEX_QUOTA = 400

#: 操作指引正文上限（字）。它不进注入，只在模型按需取全文时返回，
#: 所以可以比短规则宽得多；8000 字约等于一份完整的阅卷/立案 SOP。
PLAYBOOK_MAX_CHARS = 8000

#: 快照缓存 TTL（秒）。扩展通常在同一会话内反复拉，跨天/写记忆会主动失效。
SNAPSHOT_CACHE_TTL = 3600

#: 快照 cache key。**必须**带上版本号与锚点：
#:
#: - 不带锚点 = 把 A 案的快照发给 B 案（最严重的正确性事故）；
#: - 不带版本号 = 失效只能按人删一个 key，而同一律师现在有 N 个锚点 key，
#:   且 locmem 没有 ``delete_pattern``。版本号把「失效」降级成「自增一个
#:   整数」，所有锚点变体一次作废。
SNAPSHOT_CACHE_KEY = "agent:memory:snapshot:{user_id}:{firm_id}:{version}:{anchor}"
SNAPSHOT_VERSION_KEY = "agent:memory:snapver:{user_id}"

_KIND_LABEL: dict[str, str] = {
    AgentMemory.Kind.CORRECTION: "纠正",
    AgentMemory.Kind.PREFERENCE: "偏好",
    AgentMemory.Kind.PROCEDURE: "惯例",
    AgentMemory.Kind.FACT: "事实",
    AgentMemory.Kind.PLAYBOOK: "指引",
}


@dataclass(frozen=True)
class SnapshotLayer:
    """注入快照的一层（个人 / 团队 / 律所）。"""

    scope: str
    quota: int
    memories: tuple[AgentMemory, ...]

    @property
    def text(self) -> str:
        lines: list[str] = []
        used = 0
        playbooks: list[str] = []
        for memory in self.memories:
            content = " ".join((memory.content or "").split()).strip()
            if not content:
                continue

            # 长篇指引：**不展开正文**，只留一行索引。正文由模型按需用
            # recall_memory 取全文。直接内联会被单条 200 字闸门筛掉，
            # 律师会以为记忆没生效。
            if memory.kind == AgentMemory.Kind.PLAYBOOK or len(content) > MAX_SINGLE_ENTRY_CHARS:
                # 标题取**原始** content 的首行：上面的 content 已被压平成一整段，
                # 从那里切会把正文第一句也带出来（实测过，索引变成半截正文）。
                raw = (memory.content or "").strip()
                title = raw.split("\n", 1)[0].strip()[:40] or content[:40]
                playbooks.append(f"- {title}")
                continue

            line = f"- [{_KIND_LABEL.get(memory.kind, memory.kind)}] {content}"
            if used + len(line) > self.quota:
                break
            lines.append(line)
            used += len(line)

        if playbooks:
            # 索引行也受配额约束，但另留一小块（最多 400 字）以免挤掉短规则
            block = "\n".join(["", "需要时可用 `recall_memory(query)` 取全文的操作指引:", *playbooks])
            if used + len(block) <= self.quota + INDEX_QUOTA:
                lines.append(block)
        return "\n".join(lines)


_SCOPE_HEADER: dict[str, str] = {
    AgentMemory.Scope.LAWYER: "### 个人记忆（该律师本人的偏好与纠正，优先遵循）",
    AgentMemory.Scope.TEAM: "### 团队记忆（所在律师团队的惯例）",
    AgentMemory.Scope.LAW_FIRM: "### 律所记忆（所内规范，全所适用）",
}

_SCOPE_QUOTA: dict[str, int] = {
    AgentMemory.Scope.LAWYER: INJECT_QUOTA_LAWYER,
    AgentMemory.Scope.TEAM: INJECT_QUOTA_TEAM,
    AgentMemory.Scope.LAW_FIRM: INJECT_QUOTA_LAW_FIRM,
}


def _snapshot_version(lawyer: Lawyer) -> int:
    """当前律师的快照版本号（不存就现置 1）。"""
    return int(cache.get_or_set(SNAPSHOT_VERSION_KEY.format(user_id=lawyer.pk), 1, None) or 1)


def _bump_snapshot_version(lawyer: Lawyer) -> None:
    """让该律师**所有锚点变体**的快照失效。

    不能只删一个 key：同一个律师现在按项目/案件有 N 个快照（见
    ``SNAPSHOT_CACHE_KEY``），而 locmem 不支持 ``delete_pattern``。
    """
    key = SNAPSHOT_VERSION_KEY.format(user_id=lawyer.pk)
    try:
        cache.incr(key)
    except ValueError:
        # key 不存在或不是整数（缓存被清 / 首次写入）—— 置一个新版本即可
        cache.set(key, 2, None)


def _anchor_lines(
    notes: list[AgentMemory],
    *,
    quota: int,
    with_confirm: bool,
) -> str:
    """把一批项目笔记渲染成行（带作者与时间，受配额约束）。"""
    lines: list[str] = []
    used = 0
    for note in notes:
        content = " ".join((note.content or "").split()).strip()
        if not content:
            continue
        # Lawyer.__str__ = real_name or username（模型没有 name 字段）
        who = (str(note.lawyer) if note.lawyer_id else "") or "同事"
        stamp = note.confirmed_at or note.created_at
        when = stamp.strftime("%m-%d") if stamp else ""
        where = "本案" if note.case_id is not None else "项目"
        suffix = f"（{who} {when} 确认）" if with_confirm else f"（{who} {when}）"
        line = f"- [{where}] {content}{suffix}"
        if used + len(line) > quota:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def _anchor_block(lawyer: Lawyer, *, contract_id: int | None, case_id: int | None) -> tuple[str, list[AgentMemory]]:
    """渲染「本项目/本案」块：已确认事实在前，未确认的判断在后。

    两块的标题必须说清性质差异。混在一起的话，模型会把同事的推测当成
    已确认事实继续往下推，错误的期望值会被一轮轮放大。

    排序确定性（字节稳定）：事实按 ``(confirmed_at, id)`` 降序，判断按
    ``(created_at, id)`` 降序，同时间戳用 id 兑底。
    """
    if contract_id is None and case_id is None:
        return "", []
    queryset = (
        scopes.anchor_visible_queryset(lawyer, contract_id=contract_id, case_id=case_id)
        .select_related("lawyer")
        .order_by("id")[:200]
    )
    notes = list(queryset)
    if not notes:
        return "", []

    facts = sorted((n for n in notes if n.confirmed_at), key=lambda n: (n.confirmed_at, n.pk), reverse=True)
    judgments = sorted((n for n in notes if not n.confirmed_at), key=lambda n: (n.created_at, n.pk), reverse=True)

    blocks: list[str] = []
    injected: list[AgentMemory] = []

    fact_text = _anchor_lines(facts, quota=INJECT_QUOTA_PROJECT_FACT, with_confirm=True)
    if fact_text:
        blocks.append(
            "### 本项目已确认的事实（律师人工确认过；**与工具查到的数据冲突时，一律以工具为准**）\n" + fact_text
        )
        injected.extend(facts)

    judgment_text = _anchor_lines(judgments, quota=INJECT_QUOTA_PROJECT_JUDGMENT, with_confirm=False)
    if judgment_text:
        blocks.append("### 本项目同事的判断（来自团队其他会话，**未经确认**，需自行复核后再用）\n" + judgment_text)
        injected.extend(judgments)

    return "\n\n".join(blocks), injected


def build_snapshot(
    lawyer: Lawyer,
    *,
    contract_id: int | None = None,
    case_id: int | None = None,
    refresh: bool = False,
    refresh_reason: str = "",
) -> str:
    """渲染注入用的记忆块（Markdown）。

    带会话无关的缓存：同一律师在 TTL 内拿到完全相同的字节，保证 prompt
    cache 可命中。``refresh=True`` 用于「长期记忆刚写入」这类必须立刻可见的
    场景（对应 pi-memory 的 snapshotDirty）。
    """
    anchor = f"c{contract_id or 0}-k{case_id or 0}"
    key = SNAPSHOT_CACHE_KEY.format(
        user_id=lawyer.pk,
        firm_id=lawyer.law_firm_id or 0,
        version=_snapshot_version(lawyer),
        anchor=anchor,
    )
    if not refresh:
        cached = cache.get(key)
        if isinstance(cached, str):
            return cached

    layers: list[SnapshotLayer] = []
    for scope, kwargs in scopes.resolve_scopes(lawyer):
        # **排除项目笔记**：它们走上面的锚点块，且有「本案/他案」的区分。
        # 不排除的话，一条挂在 A 案的笔记会同时出现在 B 案会话的「个人记忆」
        # 里——等于项目隔离失效，而且同一条被注入两遍。
        queryset = AgentMemory.objects.filter(
            status=AgentMemory.Status.ACTIVE,
            contract_id__isnull=True,
            case_id__isnull=True,
            **kwargs,
        )
        memories = tuple(search._rank_by_usage(list(queryset), 40))
        layer = SnapshotLayer(scope=scope, quota=_SCOPE_QUOTA[scope], memories=memories)
        layers.append(layer)

    blocks: list[str] = []
    injected: list[AgentMemory] = []

    # 项目层排在最前：本轮到底在办哪个项目，优先级高于律师的个人偏好。
    anchor_block, anchor_notes = _anchor_block(lawyer, contract_id=contract_id, case_id=case_id)
    if anchor_block:
        blocks.append(anchor_block)
        injected.extend(anchor_notes)

    for layer in layers:
        text = layer.text
        if not text:
            continue
        blocks.append(f"{_SCOPE_HEADER[layer.scope]}\n{text}")
        injected.extend(layer.memories)

    if not blocks:
        snapshot = ""
    else:
        stamp = refresh_reason or "snapshot"
        snapshot = (
            "## 关于这位律师的记忆\n"
            f"（快照 {stamp}；如与工具查询结果冲突，一律以工具返回的数据为准）\n\n"
            + "\n\n".join(blocks)
            + "\n\n> 这些是历史沉淀的偏好与惯例，用于调整表达与做法，"
            "**不是案件事实来源**。涉及案号、当事人、金额、期限时仍需调工具核对。"
        )

    cache.set(key, snapshot, SNAPSHOT_CACHE_TTL)
    search.mark_hit(injected)
    return snapshot


def invalidate_snapshot(lawyer: Lawyer) -> None:
    """写记忆后主动失效快照（否则新记忆最慢要等 TTL 才可见）。"""
    _bump_snapshot_version(lawyer)


def _invalidate_firm_snapshots(lawyer: Lawyer) -> None:
    """律所/团队层变更后清理相关成员快照。

    没有 cache.delete_pattern 的通用保证（locmem 就没有），所以退化为
    按人删除：律所人数是几十量级，一次全删可接受。
    """
    # 跨 app 模型延迟解析（agent 不静态依赖 organization，与 session_service 同口径）
    lawyer_model = django_apps.get_model("organization", "Lawyer")

    if not lawyer.law_firm_id:
        invalidate_snapshot(lawyer)
        return
    members: Any = lawyer_model.objects.filter(law_firm_id=lawyer.law_firm_id).only("id", "law_firm_id")
    for member in members:
        invalidate_snapshot(member)
