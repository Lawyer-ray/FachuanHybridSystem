"""策展提升（团队 / 律所）—— 候选池、强制改写与 PII 闸门。

团队/律所记忆**禁止自动聚合**个人记忆（见 ``models/memory.py`` 模块注释）：
只有 ``promote_memory()``（管理员挑选 + 强制改写 + PII 闸门）这一个入口，
且每条都留 ``promoted_from`` 指针可溯源。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.apps import apps as django_apps
from django.db import transaction

from ...models import AgentMemory, content_hash_of
from . import scopes, snapshot, write

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

# ── PII 闸门 ────────────────────────────────────────────────────────────

#: 提升到团队/律所层时拦截的模式。跨人可见的记忆一旦带具体当事人信息就是
#: 保密义务问题，不是体验问题——所以这里宁可误杀。
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("身份证号", re.compile(r"\b\d{17}[\dXx]\b")),
    ("手机号", re.compile(r"\b1[3-9]\d{9}\b")),
    ("案号", re.compile(r"[（(]\s*\d{4}\s*[）)]\s*[\u4e00-\u9fa5]{0,4}\d{1,8}[\u4e00-\u9fa5]*\d*号")),
    ("银行卡号", re.compile(r"\b\d{16,19}\b")),
    # 「王某诉某公司」这类匿名化写法是安全的；「王某某诉北京某某科技有限公司」
    # 这种带完整主体名的才是问题。用「诉…公司/单位」结构 + 长度判定。
    ("完整当事人名称", re.compile(r"[\u4e00-\u9fa5]{4,20}(?:有限公司|有限责任公司|股份有限公司|事务所|中心|厂)")),
)


def scan_pii_risk(content: str) -> list[str]:
    """返回命中的敏感模式名称列表（空列表 = 通过）。

    这是**正则粗筛**，不追求完备：它的作用是拦住无心的照搬（管理员把个人
    记忆原文直接提升），不是对抗刻意规避。刻意规避由「必须改写」这一条
    制度性约束兜底。
    """
    hits: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(content or ""):
            hits.append(label)
    return hits


def promote_candidates(
    lawyer: Lawyer, *, scope: str, team_id: int | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """团队/律所策展的候选池。

    排序依据是「共识度」：同义或相近的个人记忆越多、总命中越高，排得越前。
    这些既是最安全的（多人独立得出）也是最有价值的（高频使用）。
    """
    if not scopes.can_curate_scope(lawyer, scope, team_id=team_id):
        raise ValueError("无权查看该作用域的策展候选")

    qs = scopes._curation_source_queryset(lawyer, scope=scope, team_id=team_id)

    # 已提升过的原记忆不再作为候选
    already = set(AgentMemory.objects.filter(promoted_to__isnull=False).values_list("id", flat=True))

    flattened: list[AgentMemory] = [memory for memory in qs.select_related("lawyer")[:2000] if memory.pk not in already]
    flattened.sort(key=lambda m: (-m.hit_count, -m.confidence, m.created_at))

    result: list[dict[str, Any]] = []
    for memory in flattened[:limit]:
        result.append(
            {
                "id": str(memory.pk),
                "kind": memory.kind,
                "content": memory.content,
                "hit_count": memory.hit_count,
                "from_lawyer": memory.lawyer.real_name if memory.lawyer is not None else "",
                "pii_risk": scan_pii_risk(memory.content),
            }
        )
    return result


def promote_memory(
    lawyer: Lawyer,
    *,
    source_ids: list[str],
    content: str,
    kind: str,
    scope: str,
    team_id: int | None = None,
    acknowledged_firm_wide: bool = False,
) -> AgentMemory:
    """把若干条个人记忆策展提升为团队/律所记忆。

    **强制改写**：``content`` 必须与任何一条来源记忆的原文不同。这不是形式
    要求——原样提升会把「客户 A 同意 30 万分 3 期」这类具体事实搬进全所可见
    的层级，既是保密风险，也让记忆库充满不可复用的噪音。

    **律所层需显式确认影响面**：``acknowledged_firm_wide=True`` 表示提交者
    已确认「这条规则将对全所所有律师的 AI 生效」。为什么不用双管理员会签：
    实测生产环境有只有 1 个管理员、甚至 0 个管理员的律所，强制会签会让那些
    律所完全用不了律所层。真实的约束是「你知道自己在写全所规范」，不是
    「凑够两个人盖章」。
    """
    if not scopes.can_curate_scope(lawyer, scope, team_id=team_id):
        raise ValueError("无权向该作用域提升记忆")
    if not source_ids:
        raise ValueError("必须至少选择一条来源记忆")
    if kind not in AgentMemory.Kind.values:
        raise ValueError(f"未知的记忆类型: {kind}")

    content = " ".join((content or "").split()).strip()
    if not content:
        raise ValueError("必须填写改写后的团队/律所级规则")
    if len(content) > 500:
        raise ValueError("改写后的规则过长（上限 500 字）")

    sources = list(scopes._curation_source_queryset(lawyer, scope=scope, team_id=team_id).filter(pk__in=source_ids))
    if len(sources) != len(set(source_ids)):
        raise ValueError("部分来源记忆不存在或无权访问")

    # 强制改写闸门：内容不能与任一来源原文相同
    normalized = content_hash_of(content)
    if any(content_hash_of(s.content) == normalized for s in sources):
        raise ValueError("不能原样提升个人记忆，必须改写成可复用的团队/律所级规则（脱敏）")

    pii = scan_pii_risk(content)
    if pii:
        raise ValueError(f"改写内容仍含敏感信息（{'、'.join(pii)}），请先脱敏")

    # 律所层只允许「惯例/规范」，不允许具体事实——具体事实进律所层没有正当理由
    # 注意顺序：类型闸门放在权限闸门之后，因为它只在有权限时才谈得上
    if scope == AgentMemory.Scope.LAW_FIRM and kind not in (AgentMemory.Kind.PROCEDURE, AgentMemory.Kind.PREFERENCE):
        raise ValueError("律所层只接受「惯例」或「偏好」，不接受具体事实")
    if scope == AgentMemory.Scope.LAW_FIRM and not acknowledged_firm_wide:
        raise ValueError("提升到律所层会影响全所所有律师的 AI，请先确认影响面（acknowledged_firm_wide）")

    owner: dict[str, Any] = {"law_firm": lawyer.law_firm}
    if scope == AgentMemory.Scope.TEAM:
        if team_id is None:
            raise ValueError("提升到团队必须指定 team_id")
        # 跨 app 模型延迟解析（agent 不静态依赖 organization，与 session_service 同口径）
        team_model = django_apps.get_model("organization", "Team")
        team: Any = team_model.objects.filter(pk=team_id).first()
        if team is None:
            raise ValueError("团队不存在")
        if lawyer.law_firm_id != team.law_firm_id:
            raise ValueError("不能向其他律所的团队提升记忆")
        owner = {"team": team}
    elif scope == AgentMemory.Scope.LAW_FIRM:
        if not lawyer.law_firm_id:
            raise ValueError("当前账号未归属律所")

    # S47-01（2026-11-23 二轮审计）：原 `get_or_create` 的查找条件只有
    # `scope + content_hash + status`，**缺 owner 维度** —— 别家律所/别的团队只要文本相同，
    # 就会被命中并返回对方那条记忆（越权回吐内容），而本团队该有的规则则永远不落库。
    # 查找条件必须与归属维度一致：团队按 team、律所按 law_firm、个人按 law_firm + created_by。
    if scope == AgentMemory.Scope.TEAM:
        owner_lookup: dict[str, Any] = {"team": team}
    elif scope == AgentMemory.Scope.LAW_FIRM:
        owner_lookup = {"law_firm": lawyer.law_firm}
    else:  # PERSONAL
        owner_lookup = {"law_firm": lawyer.law_firm, "created_by": lawyer}

    with transaction.atomic():
        memory, _created = AgentMemory.objects.get_or_create(
            scope=scope,
            content_hash=normalized,
            status__in=[AgentMemory.Status.PENDING, AgentMemory.Status.ACTIVE],
            **owner_lookup,
            defaults={
                "kind": kind,
                "content": content,
                "status": AgentMemory.Status.ACTIVE,
                "confidence": 1.0,
                "created_by": lawyer,
                **owner,
            },
        )
        memory.promoted_from.set(sources)

    write._ensure_embedding(memory)
    # 提升会影响所有成员，逐个失效快照（人数有限，直接按律所前缀清）
    snapshot._invalidate_firm_snapshots(lawyer)
    return memory
