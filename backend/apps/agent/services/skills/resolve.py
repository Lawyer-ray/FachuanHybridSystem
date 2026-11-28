"""解析「某个律师这一轮看到什么技能」——**唯一解析入口**。

任何地方（``/skill:`` 展开、系统提示索引、MCP 按需读取、管理抽屉清单）都必须
经过本模块，不许自己拼「内置 + 个人 + 共享」的并集。级联去重、偏好过滤、影子
关系、双轨正文取值只有一份实现，四份各自演化的后果是「抽屉里看得见、模型用不上」。

## 两条出口，服务两类完全不同的消费者

- ``resolve_for_user``：**运行时交付面**。只有「真的会被交付给模型」的条目，
  共享技能取 ``published_revision``（线上已审批版），个人技能取本体。
- ``list_visible_skills``：**管理抽屉面**。该律师能看到的**全部**条目，含被遮蔽
  的、本人草稿/待审的、管理员可见的本所待审与已下线。

两条出口分开是 2026-11 二轮审计的结论。P0 只有一个 ``visible_skills``，它把列表
折叠成 winners-only，于是「被我的同名技能遮蔽的所内技能」在「所内」tab 里凭空
消失——律师会觉得所内根本没发过那条技能。

## 四步解析（顺序不能换）

1. **候选集**：内置 ∪ 个人(``ACTIVE``) ∪ 所属律师团队共享(``ACTIVE`` 且有
   ``published_revision``) ∪ 所属律所共享(同条件)。
2. **先按偏好过滤 ``enabled``**（**不是**先去重再过滤）。
3. **再按 ``name`` 级联去重**：内置(-1) > 个人(0) > 团队(1) > 所内(2)。
4. **稳定排序** ``(scope_weight, name)``——**绝不按 ``updated_at``**，那会让
   每轮系统提示前缀随机变化，prompt cache 全线失效。

第 2 步与第 3 步的顺序是语义而不是实现细节：律师把自己那份同名个人技能关掉，
期望的是「回落到所内版」，而不是「这个名字从此消失」。先去重的话，个人版赢了
之后被 ``enabled=False`` 踢出，所内版早已在去重时被判负删掉，两边一起没了。

## 同层同名怎么决胜

同一层可能有多个团队都发了同名技能。用 ``(updated_at desc, str(pk))`` 取一个
**确定性**赢家：只按 ``updated_at`` 的话，同秒创建的两条会在不同进程里给出不同
答案（``updated_at`` 相同时数据库返回顺序不保证），表现为「同一个所里两个律师
看到的同名技能内容不同」——这种不一致没有任何报错。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.agent.models import AgentSkill, AgentSkillPreference

from . import flags, permissions
from .constants import BUILTIN_PREFIX, SCOPE_WEIGHT, USER_PREFIX
from .library import builtin_skills

logger = logging.getLogger(__name__)

#: 共享技能的作用域集合（走双轨发布）
_SHARED_SCOPES = (AgentSkill.Scope.TEAM, AgentSkill.Scope.LAW_FIRM)


def resolve_for_user(user_id: int | None) -> list[dict]:
    """本轮**可交付**的技能（已启用且已生效）。

    ``user_id is None``（后台任务 / 测试）时只返内置：没有用户身份就没有偏好、
    没有团队归属，把任何一条数据库技能交付出去都是越权。
    """
    entries = _candidates(user_id)
    enabled = [entry for entry in entries if entry["enabled"]]
    winners = _cascade(enabled)
    ordered = sorted(winners, key=lambda item: (item["scope_weight"], item["name"]))
    return ordered


def list_visible_skills(*, user_id: int) -> list[dict]:
    """该律师可见的全部技能（管理抽屉用；含被遮蔽者与草稿）。

    每条的 ``effective`` 表示「本轮是否真的会交付给模型」，``shadowed_by`` 指出
    它被谁顶掉了。前端据此显示「被我的同名技能覆盖」这类提示，而不是让条目
    静默消失。
    """
    lawyer = _lawyer(user_id)
    candidates = _candidates(user_id, include_unpublished=True, lawyer=lawyer)
    # 可见性不是「候选集里有」就算：管理者例外（查看草稿/待审/已下线）必须逐条
    # 过 ``permissions.can_view``。不过这道闸门的话，全所每一条别人的草稿都会出现
    # 在每个人的抽屉里——那比不发布更糟（半成品指令最容易被误当规范照做）。
    entries = [
        entry
        for entry in candidates
        if entry.get("_row") is None or permissions.can_view(lawyer, entry["_row"])
    ]
    winners = {entry["name"]: entry for entry in _cascade([e for e in entries if e["enabled"]])}

    result: list[dict] = []
    for entry in entries:
        winner = winners.get(entry["name"])
        is_effective = winner is not None and winner["key"] == entry["key"]
        shadowed_by = None
        if entry["enabled"] and winner is not None and not is_effective:
            shadowed_by = {
                "key": winner["key"],
                "scope": winner["scope"],
                "title": winner["title"],
            }
        enriched = {
            **entry,
            "effective": is_effective,
            "shadowed_by": shadowed_by,
        }
        enriched.update(permissions.capability_flags(lawyer, entry.get("_row")))
        result.append(_public(enriched))
    # 管理面按「来源层级 → 名字」排：所内/团队在上，个人在下，与级联优先级逆转，
    # 因为抽屉里律师先看「所里发了什么」再看「我自己加了什么」。
    return sorted(result, key=lambda item: (-item["scope_weight"], item["name"]))


def _public(entry: dict) -> dict:
    """去掉内部字段与服务端专用的正文。

    ``_row`` 是 ORM 实例（不能跨层传也不会被序列化）；``body`` 是交付正文，
    清单里不需要——所内 60 条 × 32KB 会把抽屉的首屏响应拖成兆级，而抽屉真正
    要正文时走 ``get_detail``（单条）或 ``content_for_ref``（运行时）。
    """
    return {key: value for key, value in entry.items() if key not in ("body",) and not key.startswith("_")}


# ── 候选集 ────────────────────────────────────────────────────


def _lawyer(user_id: int | None) -> Any:
    if user_id is None:
        return None
    from apps.organization.models import Lawyer

    return Lawyer.objects.select_related("law_firm").prefetch_related("lawyer_teams").filter(pk=user_id).first()


def _candidates(user_id: int | None, *, include_unpublished: bool = False, lawyer: Any = None) -> list[dict]:
    """候选集（未过滤偏好、未去重）。顺序无关——后面两步都会重排。"""
    builtin_disabled = _disabled_builtin_keys(user_id) if user_id is not None else set()
    entries: list[dict] = [{**entry, "enabled": entry["key"] not in builtin_disabled} for entry in builtin_skills()]
    if user_id is None or not flags.user_skills_enabled():
        # 无用户身份 = 无偏好、无团队归属；总开关 off = 只留内置（面盘回滚）。
        return entries

    lawyer = lawyer if lawyer is not None else _lawyer(user_id)
    entries.extend(_personal_entries(user_id, include_unpublished=include_unpublished))
    entries.extend(
        _shared_entries(
            lawyer,
            include_unpublished=include_unpublished,
            disabled_keys=_disabled_shared_keys(user_id),
        )
    )
    return entries


def _personal_entries(user_id: int, *, include_unpublished: bool) -> list[dict]:
    """个人技能：``enabled`` 是本体字段（个人没有偏好行）。"""
    queryset = AgentSkill.objects.filter(lawyer_id=user_id, scope=AgentSkill.Scope.LAWYER)
    if not include_unpublished:
        queryset = queryset.filter(status=AgentSkill.Status.ACTIVE)
    rows = queryset.order_by("name")
    return [_entry_from_row(row, body=row.body) for row in rows]


def _shared_entries(lawyer: Any, *, include_unpublished: bool, disabled_keys: set[str]) -> list[dict]:
    """团队 + 所内技能。

    运行时（``include_unpublished=False``）只认 ``status=active`` 且
    ``published_revision`` 非空，正文取 ``published_revision``——这是双轨发布
    的核心：工作区草稿怎么改都不影响线上。

    管理面（``include_unpublished=True``）额外包含本人可见的草稿/待审/已下线，
    但**仍然**只为共享技能提供 ``published_revision`` 的正文（工作区正文由
    ``get_detail`` 单独给，避免列表把 KB 级正文全拖出来）。
    """
    if lawyer is None:
        return []
    firm_id = getattr(lawyer, "law_firm_id", None)
    if firm_id is None:
        # 无律所律师不参与任何共享作用域。绝不能把 law_firm_id=None 当成一个租户去匹配。
        return []
    team_ids = permissions._team_ids(lawyer)

    queryset = (
        AgentSkill.objects.select_related("team", "published_revision")
        .filter(scope__in=_SHARED_SCOPES)
        .filter(
            # 团队：只看自己所属的团队；所内：只看自己的律所。两段 OR 而不是
            # 一个 filter(Q(team__in=...) | Q(law_firm=firm))，防止把「别的律所
            # 但团队 id 恰好相同」之类的情况混进来（id 是全局的，但语义要写死）。
            _shared_scope_filter(team_ids=team_ids, firm_id=firm_id)
        )
    )
    if not include_unpublished:
        queryset = queryset.filter(status=AgentSkill.Status.ACTIVE, published_revision__isnull=False)

    entries: list[dict] = []
    for row in queryset:
        if not permissions.same_firm(lawyer, row):
            continue
        revision = row.published_revision
        entry = _entry_from_row(
            row,
            body=revision.body if revision is not None else "",
            title=revision.title if revision is not None else row.title,
            description=revision.description if revision is not None else row.description,
            version=revision.version if revision is not None else row.version,
        )
        entry["enabled"] = entry["key"] not in disabled_keys
        entries.append(entry)
    return entries


def _shared_scope_filter(*, team_ids: set[int], firm_id: int) -> Any:
    from django.db.models import Q

    condition = Q(scope=AgentSkill.Scope.LAW_FIRM, law_firm_id=firm_id)
    if team_ids:
        condition |= Q(scope=AgentSkill.Scope.TEAM, team_id__in=team_ids)
    return condition


def _entry_from_row(
    row: AgentSkill,
    *,
    body: str,
    title: str | None = None,
    description: str | None = None,
    version: int | None = None,
) -> dict:
    """ORM 行 → 解析条目（字段集见 CONTRACT §2）。"""
    scope = str(row.scope)
    return {
        "key": f"{USER_PREFIX}{row.pk}",
        "name": row.name,
        "title": title if title is not None else row.title,
        "description": description if description is not None else row.description,
        "scope": scope,
        "scope_weight": SCOPE_WEIGHT.get(scope, len(SCOPE_WEIGHT)),
        "source": "user" if scope == AgentSkill.Scope.LAWYER else scope,
        "enabled": bool(row.enabled),
        "editable": bool(row.status != AgentSkill.Status.ARCHIVED),
        "version": version if version is not None else row.version,
        "body": body,
        "status": str(row.status),
        "review_status": str(row.review_status),
        "review_note": row.review_note or "",
        # ``version`` 已被上游覆写成「线上生效版」的版本号（共享技能），所以
        # 线上版本就是它；个人技能没有线上/工作区之分，两者相等。
        "published_version": version if version is not None else row.version,
        "has_unpublished_changes": bool(row.published_revision_id) and row.version != (version or row.version),
        "shadowed": [],
        # 内部字段：列表出口会剔掉，权限计算需要原始行
        "_row": row,
    }


# ── 偏好 ──────────────────────────────────────────────────────


def _disabled_builtin_keys(user_id: int | None) -> set[str]:
    if user_id is None:
        return set()
    return set(
        AgentSkillPreference.objects.filter(
            user_id=user_id,
            enabled=False,
            skill_key__startswith=BUILTIN_PREFIX,
        ).values_list("skill_key", flat=True)
    )


def _disabled_shared_keys(user_id: int) -> set[str]:
    """共享技能被本人停用的 key 集合。

    与内置技能同一张偏好表（``skill:<uuid>`` 行），但**只有** ``scope`` 是团队/
    所内的技能会去看它：个人技能的启停是本体字段 ``enabled``，共用这张表会让
    「PATCH 一个共享技能」与「PATCH 自己的技能」写两处不同地方，接口语义分裂。
    """
    return set(
        AgentSkillPreference.objects.filter(
            user_id=user_id,
            enabled=False,
            skill_key__startswith=USER_PREFIX,
        ).values_list("skill_key", flat=True)
    )


# ── 级联 ──────────────────────────────────────────────────────


def _cascade(entries: list[dict]) -> list[dict]:
    """按 ``name`` 级联去重；赢家收集败者进 ``shadowed``。"""
    buckets: dict[str, list[dict]] = {}
    for entry in entries:
        buckets.setdefault(entry["name"], []).append(entry)

    winners: list[dict] = []
    for name, group in buckets.items():
        group.sort(key=_winner_sort_key)
        winner = dict(group[0])
        winner["shadowed"] = [
            {"key": loser["key"], "scope": loser["scope"], "title": loser["title"]} for loser in group[1:]
        ]
        winners.append(winner)
    return winners


def _winner_sort_key(entry: dict) -> tuple[int, int, str]:
    """级联决胜键：层级优先 → 越新越优 → id 字符串兜底（确定性）。"""
    row = entry.get("_row")
    updated = getattr(row, "updated_at", None)
    # ``updated_at`` 转成负的微秒数让「越新越靠前」；缺失记 0（不参与）。内置条目
    # 没有行，也不会和同层比（它是唯一的 -1 层）。
    recency = -int(updated.timestamp() * 1_000_000) if updated is not None else 0
    return (entry["scope_weight"], recency, str(entry["key"]))
