"""技能 CRUD 门面：个人技能全生命周期 + 共享技能的工作区编辑。

## 为什么这里没有「落盘」

P0 曾把每条技能物化成 ``$AGENT_HOME/skills/<uid>/<name>/SKILL.md`` 再逐个
``--skill`` 注入 pi。2026-11-28 的二轮审计在 pi 1.6.0 源码里确认了两件事：
没有 ``read``/``bash`` 工具时 pi **根本不生成** ``<available_skills>``（所以
``--skill`` 带不来任何自主发现能力），而原生 ``/skill:`` 只认
``text.startsWith("/skill:")``（所以案件/合同页前置的 ``[当前业务：…]`` 锚点会让
它**静默失效**）。同时 ``codex`` 与 ``cline`` 两个后端并未封住内置文件读取工具，
把别人的技能目录落到同 UID 的磁盘上就是一条真实的跨用户泄密面。

结论：取消物化，DB 直出（方案 A，见 ``docs/analysis/user-skills-copilot-2026-11-28/``）。
交付改由 ``expand.py``（点名）+ ``prompt_block.py``（索引）+ MCP ``get_agent_skill``
（按需取全文）三条通道完成，它们都只读本模块所属包里的 ``resolve``——本模块
不再有任何磁盘副作用，也就不需要 ``on_commit`` 竞态、目录迁移与 reconcile。

## 三条写路径的共同纪律

1. **``key`` 是身份，``name`` 建后不可改**：改名等于断偏好（偏好按 key 记）与
   审计链（快照按 skill 归属），所以 ``name`` 只在创建时定。
2. **已归档的技能不可编辑/启停**：否则一次 ``PUT`` 就能把下线了的指令重新写回
   可交付状态，绕过审批（P0 的 ``_own_skill`` 没过滤 ``status``，这是个真 bug）。
3. **共享技能的编辑只改工作区**：``status`` 与 ``published_revision`` 都不动，
   只把 ``review_status`` 置 ``pending``。线上交付继续用已批准的那一版
   （详见 ``review.py`` 的双轨说明）。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import string
import uuid
from typing import Any

from django.db import IntegrityError, connection, transaction

from apps.agent.models import AgentSkill, AgentSkillPreference, AgentSkillRevision

from . import flags, library, permissions, resolve, review, validation
from .constants import (
    BUILTIN_PREFIX,
    CONTENT_PAGE_BYTES,
    MAX_SHARED_SKILLS,
    MAX_TITLE,
    MAX_USER_SKILLS,
    UNAVAILABLE_DISABLED,
    UNAVAILABLE_MISSING,
    UNAVAILABLE_NOT_PUBLISHED,
    USER_PREFIX,
)
from .errors import SkillConflict, SkillForbidden, SkillInvalid, SkillNotFound, SkillQuotaExceeded
from .render import render_skill_body, render_skill_md

logger = logging.getLogger(__name__)

_GENERATED_ALPHABET = string.digits + string.ascii_lowercase


# ── 读 ────────────────────────────────────────────────────────


def list_for_user(user_id: int) -> list[dict]:
    """管理抽屉清单：可见的全部条目（含被遮蔽、草稿、待审）。"""
    return resolve.list_visible_skills(user_id=user_id)


def quota_for_user(user_id: int) -> dict:
    """配额占用：个人与共享分开计数（共享按「本所/本团队已发布条目」）。"""
    by_scope = {
        "lawyer": _quota_used(user_id, AgentSkill.Scope.LAWYER),
        "team": 0,
        "law_firm": 0,
    }
    lawyer = _lawyer_or_none(user_id)
    if lawyer is not None and getattr(lawyer, "law_firm_id", None) is not None:
        by_scope["law_firm"] = (
            AgentSkill.objects.filter(
                scope=AgentSkill.Scope.LAW_FIRM,
                law_firm_id=lawyer.law_firm_id,
            )
            .exclude(status=AgentSkill.Status.ARCHIVED)
            .count()
        )
        team_ids = permissions._team_ids(lawyer)
        if team_ids:
            by_scope["team"] = (
                AgentSkill.objects.filter(scope=AgentSkill.Scope.TEAM, team_id__in=team_ids)
                .exclude(status=AgentSkill.Status.ARCHIVED)
                .count()
            )
    return {
        "max_skills": MAX_USER_SKILLS,
        "used": by_scope["lawyer"],
        "by_scope": by_scope,
        "max_by_scope": {"lawyer": MAX_USER_SKILLS, **MAX_SHARED_SKILLS},
        # 「能不能建所内技能」与「能不能把这条提到所内」都由服务端算：
        # 前端只要渲染布尔，永远不判 is_admin（见 permissions 模块 docstring）。
        "can_create_firm": permissions.can_create_firm(lawyer) if lawyer is not None else False,
        "promotable_scopes": permissions.promotable_scopes(lawyer) if lawyer is not None else [],
    }


def get_detail(user_id: int, key: str) -> dict:
    """技能详情（管理面）：工作区最新正文 + 双轨状态。

    内置技能看文件；数据库技能看本体（**不是** ``published_revision``——作者
    要能接着编辑自己的工作区）。运行时正文走 ``content_for_ref``。
    """
    builtin = _builtin_by_key(key)
    if builtin is not None:
        body = library.read_body(builtin["name"])
        return {
            **builtin,
            "enabled": _builtin_enabled(user_id, builtin["name"]),
            # ``library.builtin_skills()`` 没有覆盖关系（只有 ``list_visible_skills``
            # 跑过级联才知道谁遮蔽谁），但详情回执必须与 ``entry_for_row`` 同形——
            # 形状不一致时前端一定会在某个分支上读到 ``undefined``。
            "shadowed": [],
            # 内置条目没有数据库行，动作权限一律 False；但**字段必须在**，否则按完整
            # 字段集声明的 SkillDetailOut 直接 500——症状是「内置技能详情打不开」，
            # 与真正的权限问题看起来毫无关系。
            **permissions.capability_flags(None, None),
            "body": body,
            "preview": render_skill_body(scope="builtin", name=builtin["name"], title=builtin["title"], body=body),
        }
    skill = _resolve_skill_row(user_id, key)
    lawyer = _lawyer_or_none(user_id)
    if not permissions.can_view(lawyer, skill):
        raise SkillNotFound("技能不存在")
    return {
        **entry_for_row(skill, lawyer),
        "body": skill.body,
        "preview": render_skill_body(scope=str(skill.scope), name=skill.name, title=skill.title, body=skill.body),
    }


def content_for_ref(user_id: int, ref: str, *, start: int = 0, limit: int = CONTENT_PAGE_BYTES) -> dict:
    """**运行时**正文（MCP ``get_agent_skill`` 的唯一数据源）。

    严格走 ``resolve_for_user``：只交付「已生效 + 本人未停用 + 共享取
    ``published_revision``」的条目。已停用 / 草稿 / 无权一律 404——这条出口给的是
    模型，不能像管理面那样把工作区草稿也返出去。

    ``ref`` 同时接受 ``builtin:<name>`` / ``skill:<uuid>`` / 裸 ``name``：模型只
    知道名字（``/skill:`` 后面跟的也是名字），API 路径参数却常带 key，两边都得认。

    Raises:
        SkillNotFound: 不在可交付集合里（含「已停用」——不解释区别，避免探测）。
    """
    if start < 0:
        raise SkillInvalid([{"field": "start", "message": "start 不能为负数"}])
    winner = _find_deliverable(user_id, ref)
    if winner is None:
        raise SkillNotFound("技能不存在或未启用")
    # 内置条目来自 ``library.builtin_skills()``，那份字典刻意不带正文（它带 mtime
    # 缓存，正文进缓存会让律师正在改的大文件常驻内存），所以这里单独读文件。
    body = winner.get("body")
    if body is None:
        body = library.read_body(winner["name"])
    rendered = render_skill_body(scope=winner["scope"], name=winner["name"], title=winner["title"], body=body)
    payload = rendered.encode("utf-8")
    total = len(payload)
    page_size = max(1, min(int(limit or CONTENT_PAGE_BYTES), CONTENT_PAGE_BYTES))
    if start > total:
        raise SkillInvalid([{"field": "start", "message": "start 超出正文长度"}])
    page = payload[start : start + page_size]
    # UTF-8 安全切分：末尾若落在多字节字符中间，会被解码成 U+FFFD。宁可少回几个
    # 字节也不能返回乱码——模型会把乱码当成正文内容照抄。
    page = _drop_partial_tail(page)
    next_start = start + len(page)
    return {
        "key": winner["key"],
        "name": winner["name"],
        "title": winner["title"],
        "scope": winner["scope"],
        "version": winner.get("version", 0),
        "content": page.decode("utf-8", errors="replace"),
        "start": start,
        "total_bytes": total,
        "truncated": next_start < total,
        "next_start": next_start if next_start < total else None,
    }


def content_unavailable_reason(user_id: int, ref: str) -> str:
    """``content_for_ref`` 取不到时，「为什么」是什么——三条出口都 404，但原因必须能区分。

    为什么值得多查两次库：这条出口的消费者是**模型**。它拿到「技能不存在」时的典型反应是
    「工具坏了」或换名字重试三次；拿到「未发布」才会想到「我该直接用上下文里那份全文」。

    为什么不能区分「存在但你无权看」：那是一个存在性探测口。所以 ``can_view`` 不成立时，
    一律回到「技能不存在」，与真的不存在共用一句话。
    """
    try:
        row = _resolve_skill_row(user_id, ref)
    except SkillNotFound:
        return UNAVAILABLE_MISSING
    lawyer = _lawyer_or_none(user_id)
    if not permissions.can_view(lawyer, row):
        return UNAVAILABLE_MISSING
    if row.scope == AgentSkill.Scope.LAWYER:
        if not row.enabled:
            return UNAVAILABLE_DISABLED
        return UNAVAILABLE_MISSING if row.status == AgentSkill.Status.ACTIVE else UNAVAILABLE_NOT_PUBLISHED
    # 共享技能：本人偏好关掉 → 停用；还没批准（或已下线）→ 未发布
    if AgentSkillPreference.objects.filter(user_id=user_id, skill_key=f"{USER_PREFIX}{row.pk}", enabled=False).exists():
        return UNAVAILABLE_DISABLED
    if row.status != AgentSkill.Status.ACTIVE or row.published_revision_id is None:
        return UNAVAILABLE_NOT_PUBLISHED
    return UNAVAILABLE_MISSING


def validate_form(*, user_id: int, name: str | None, title: str, description: str, body: str) -> dict:
    """``POST /skills/validate``：字段级错误 + 渲染预览 + 安全告警（不落库）。"""
    payload = validation.normalize_payload(name=name, title=title, description=description, body=body)
    errors = validation.validate_payload(payload, require_name=False, taken_names=_taken_names(user_id))
    preview = render_skill_md(payload["name"] or "skill-preview", payload["description"], payload["body"])
    return {
        "ok": not errors,
        "errors": errors,
        "preview": preview,
        "safety": _scan_findings(payload),
    }


# ── 写 ────────────────────────────────────────────────────────


def create_skill(
    *,
    user_id: int,
    name: str | None,
    title: str,
    description: str,
    body: str,
    source: str = "manual",
    scope: str = AgentSkill.Scope.LAWYER,
    team_id: int | None = None,
) -> dict:
    """新建技能（``name`` 可省略 → 后端生成 ``skill-<6位base36>``）。

    ``scope=law_firm`` 需要本所管理员；``scope=team`` 需要团队成员且必须给
    ``team_id``。共享技能创建后是 ``draft``：没走审批的共享指令不进交付面。
    """
    _require_writes()
    payload = validation.normalize_payload(name=name, title=title, description=description, body=body)
    taken = _taken_names(user_id) if scope == AgentSkill.Scope.LAWYER else set()
    conflict = _name_conflict(payload["name"], taken)
    if conflict:
        raise SkillConflict(conflict)
    errors = validation.validate_payload(payload, require_name=False)
    if errors:
        raise SkillInvalid(errors)
    if not payload["name"]:
        payload["name"] = _generate_name(taken)

    lawyer = _lawyer_or_none(user_id)
    owner = _owner_fields(lawyer, scope, team_id)
    is_shared = scope in (AgentSkill.Scope.TEAM, AgentSkill.Scope.LAW_FIRM)

    with transaction.atomic():
        if not is_shared:
            # 配额必须与插入同一事务、并串行化：否则两个并发创建都读到 used=19，
            # 双双落库（20 上限被破）。手法同 doc_workspace 的 _acquire_seq_lock。
            _lock_quota(user_id)
            if _quota_used(user_id, AgentSkill.Scope.LAWYER) >= MAX_USER_SKILLS:
                raise SkillQuotaExceeded(f"个人技能最多 {MAX_USER_SKILLS} 个，请先删除不用的技能")
        _check_shared_quota(scope, owner)
        try:
            skill = AgentSkill.objects.create(
                scope=scope,
                name=payload["name"],
                title=payload["title"],
                description=payload["description"],
                body=payload["body"],
                status=AgentSkill.Status.DRAFT if is_shared else AgentSkill.Status.ACTIVE,
                review_status=AgentSkill.ReviewStatus.NONE,
                enabled=True,
                source=source,
                version=1,
                created_by_id=user_id,
                **owner,
            )
        except IntegrityError as exc:
            raise SkillConflict(f"技能名「{payload['name']}」已被占用") from exc
        revision = _write_revision(skill, edited_by_id=user_id)
        if not is_shared:
            # 个人技能没有审批环节：自己就是线上，创建即生效。
            skill.published_revision = revision
            skill.activated_at = skill.created_at
            skill.save(update_fields=["published_revision", "activated_at"])
        review.prune_revisions(skill)
    return {**entry_for_row(skill, _lawyer_or_none(user_id)), "body": skill.body}


def update_skill(*, user_id: int, key: str, title: str, description: str, body: str, expected_version: int) -> dict:
    """按 ``expected_version`` 乐观锁更新工作区；共享技能顺带置 ``pending``。"""
    _require_writes()
    payload = validation.normalize_payload(name=None, title=title, description=description, body=body)
    errors = validation.validate_payload(payload, require_name=False)
    if errors:
        raise SkillInvalid(errors)
    lawyer = _lawyer_or_none(user_id)
    with transaction.atomic():
        skill = _resolve_skill_row(user_id, key, for_update=True)
        if not permissions.can_edit(lawyer, skill):
            raise SkillForbidden("你没有编辑这条技能的权限")
        _require_editable(skill)
        if skill.version != expected_version:
            raise SkillConflict(f"技能已被修改（当前 v{skill.version}），请刷新后重试")
        skill.title = payload["title"]
        skill.description = payload["description"]
        skill.body = payload["body"]
        skill.version += 1
        fields = ["title", "description", "body", "version", "updated_at"]
        if skill.is_shared:
            skill.review_status = AgentSkill.ReviewStatus.PENDING
            fields += ["review_status"]
        skill.save(update_fields=fields)
        revision = _write_revision(skill, edited_by_id=user_id)
        review.prune_revisions(skill)
        if not skill.is_shared:
            # 个人技能保存即生效：线上指针跟着工作区走，快照链保持自洽。
            skill.published_revision = revision
            skill.activated_at = skill.activated_at or skill.updated_at
            skill.save(update_fields=["published_revision", "activated_at"])
    return {**entry_for_row(skill, _lawyer_or_none(user_id)), "body": skill.body}


def delete_skill(*, user_id: int, key: str) -> None:
    """删除技能（内置 → 403；别人的 → 404；共享 → 只有审批人可删）。"""
    _require_writes()
    if _builtin_by_key(key) is not None:
        raise SkillForbidden("内置技能不能删除，只能停用")
    lawyer = _lawyer_or_none(user_id)
    with transaction.atomic():
        skill = _resolve_skill_row(user_id, key)
        if skill.scope == AgentSkill.Scope.LAWYER:
            if skill.lawyer_id != user_id:
                raise SkillNotFound("技能不存在")
        elif not permissions.can_review(lawyer, skill):
            raise SkillForbidden("共享技能只能由本所管理员删除")
        skill_key = f"{USER_PREFIX}{skill.pk}"
        skill.delete()
        # 偏好行没有外键（内置技能没有数据库行），删技能必须顺手清，
        # 否则同一个 uuid 若被复用会继承上一条的启停态。
        AgentSkillPreference.objects.filter(skill_key=skill_key).delete()


def set_enabled(*, user_id: int, key: str, enabled: bool) -> dict:
    """启停：内置与**共享**技能写偏好行；个人技能写本体 ``enabled``。

    共享技能必须只写偏好：``AgentSkill.enabled`` 是**全所共用的一行**，一个普通
    律师点开关就把全所的技能关掉——这是 2026-11 二轮审计点出的写穿风险。
    """
    _require_writes()
    builtin = _builtin_by_key(key)
    if builtin is not None:
        AgentSkillPreference.objects.update_or_create(
            user_id=user_id, skill_key=builtin["key"], defaults={"enabled": enabled}
        )
        return {"key": builtin["key"], "enabled": enabled}
    with transaction.atomic():
        skill = _resolve_skill_row(user_id, key, for_update=True)
        normalized = f"{USER_PREFIX}{skill.pk}"
        if skill.is_shared:
            if not _deliverable(user_id, normalized):
                raise SkillNotFound("技能不存在")
            AgentSkillPreference.objects.update_or_create(
                user_id=user_id, skill_key=normalized, defaults={"enabled": enabled}
            )
            return {"key": normalized, "enabled": enabled}
        if skill.lawyer_id != user_id:
            raise SkillNotFound("技能不存在")
        _require_editable(skill)
        skill.enabled = enabled
        skill.save(update_fields=["enabled", "updated_at"])
    return {"key": normalized, "enabled": enabled}


def duplicate_builtin(*, user_id: int, key: str) -> dict:
    """「复制为我的」：内置技能 → 新个人技能（内置名是保留字，名字加 ``-copy``）。"""
    builtin = _builtin_by_key(key)
    if builtin is None:
        raise SkillForbidden("只有内置技能可以复制为我的")
    return create_skill(
        user_id=user_id,
        name=_unique_name(f"{builtin['name']}-copy", _taken_names(user_id)),
        title=f"{builtin['title']}（我的）"[:MAX_TITLE],
        description=builtin["description"],
        body=library.read_body(builtin["name"]),
        source="builtin",
    )


# ── 供 review / API 复用 ──────────────────────────────────────


def entry_for_row(skill: AgentSkill, lawyer: Any | None = None) -> dict:
    """ORM 行 → 管理面条目（字段集见 CONTRACT §2）。

    ``lawyer`` 传进来才带 ``can_*``：动作权限必须服务端算（前端不得自判
    ``is_admin``）。不传时一律 ``False``——宁可按钮不出现，也不给一个点了就 403 的
    按钮（那比没有更糟，律师会以为是自己没权限而不是界面错了）。
    """
    published = skill.published_revision
    return {
        "key": f"{USER_PREFIX}{skill.pk}",
        "name": skill.name,
        "title": skill.title,
        "description": skill.description,
        "enabled": bool(skill.enabled),
        "source": "user" if skill.scope == AgentSkill.Scope.LAWYER else str(skill.scope),
        "scope": str(skill.scope),
        "scope_weight": resolve.SCOPE_WEIGHT.get(str(skill.scope), 9),
        "editable": skill.status != AgentSkill.Status.ARCHIVED,
        "version": skill.version,
        "status": str(skill.status),
        "review_status": str(skill.review_status),
        "review_note": skill.review_note or "",
        "published_version": published.version if published is not None else skill.version,
        "has_unpublished_changes": bool(published is not None and published.version != skill.version),
        "shadowed": [],
        **permissions.capability_flags(lawyer, skill if lawyer is not None else None),
    }


def _resolve_skill_row(user_id: int, key: str, *, for_update: bool = False) -> AgentSkill:
    """``skill:<uuid>`` / 裸 uuid / 裸 name → 数据库行。

    Raises:
        SkillNotFound: 找不到，或不在该律师的可见范围内（不区分两者：不泄漏存在性）。
    """
    queryset = AgentSkill.objects.select_related("team", "published_revision")
    if for_update:
        # ``team`` / ``published_revision`` 都是可空外键，``select_related`` 会拼
        # LEFT OUTER JOIN，而 PostgreSQL 的 ``FOR UPDATE`` 不允许作用在 outer join
        # 的可空侧（NotSupportedError: FOR UPDATE cannot be applied to the nullable
        # side of an outer join）。``of=("self",)`` 把加锁范围限定在主表：join 侧只读
        # 不锁，一条 SQL 仍拿全关联对象（不会退化成 N+1）。这条路径覆盖 PUT / PATCH /
        # submit / approve / reject / archive / restore / discard-draft 全部写端点。
        queryset = queryset.select_for_update(of=("self",))
    raw = (key or "").strip()
    skill: AgentSkill | None = None
    if raw.startswith(USER_PREFIX):
        raw = raw[len(USER_PREFIX) :]
    try:
        skill = queryset.filter(pk=uuid.UUID(raw)).first()
    except ValueError:
        # 裸名字：只在「本人可见」范围内找。同名跨层是常态，这里必须限定范围，
        # 否则一个团队技能被同名的所内技能顶掉时，管理员会改到看不见的那一条。
        candidates = queryset.filter(name=raw)
        lawyer = _lawyer_or_none(user_id)
        for candidate in candidates:
            if permissions.can_view(lawyer, candidate):
                skill = candidate
                break
    if skill is None:
        raise SkillNotFound("技能不存在")
    return skill


def _find_deliverable(user_id: int | None, ref: str) -> dict | None:
    """在 ``resolve_for_user`` 的结果里按 key 或 name 找一条（运行时唯一入口）。"""
    raw = (ref or "").strip()
    if not raw:
        return None
    for entry in resolve.resolve_for_user(user_id):
        if entry["key"] == raw or entry["name"] == raw:
            return entry
    # 允许 ``/content`` 直接传 uuid
    if not raw.startswith(BUILTIN_PREFIX):
        candidate = f"{USER_PREFIX}{raw}"
        for entry in resolve.resolve_for_user(user_id):
            if entry["key"] == candidate:
                return entry
    return None


def _deliverable(user_id: int, key: str) -> dict | None:
    for entry in resolve.resolve_for_user(user_id):
        if entry["key"] == key:
            return entry
    return None


# ── 内部工具 ──────────────────────────────────────────────────


def _require_writes() -> None:
    """``FACHUAN_AGENT_USER_SKILLS=off`` 时写接口一律 503（读保留取证）。"""
    if not flags.writes_enabled():
        raise SkillForbidden("技能写入已被运营开关关闭，请联系管理员")


def _require_editable(skill: AgentSkill) -> None:
    """已归档技能不可编辑/启停（见模块 docstring 第 2 条）。"""
    if skill.status == AgentSkill.Status.ARCHIVED:
        raise SkillConflict("这条技能已下线，请先恢复再编辑")


def _owner_fields(lawyer: Any, scope: str, team_id: int | None) -> dict:
    """按作用域给出归属字段（CHECK 约束要求恰好一个非空）。"""
    if lawyer is None:
        raise SkillNotFound("技能不存在")
    if scope == AgentSkill.Scope.LAWYER:
        return {"lawyer_id": getattr(lawyer, "pk", None)}
    if scope == AgentSkill.Scope.LAW_FIRM:
        if not permissions.can_create_firm(lawyer):
            raise SkillForbidden("只有本所管理员可以新建所内技能")
        return {"law_firm_id": getattr(lawyer, "law_firm_id", None)}
    if scope == AgentSkill.Scope.TEAM:
        team = _team_for(lawyer, team_id)
        if team is None or not permissions.can_create_team(lawyer, team):
            raise SkillForbidden("你没有在该团队新建技能的权限")
        return {"team_id": team.pk}
    raise SkillInvalid([{"field": "scope", "message": "作用域只能是 lawyer / team / law_firm"}])


def _team_for(lawyer: Any, team_id: int | None) -> Any | None:
    from apps.organization.models import Team

    teams = getattr(lawyer, "lawyer_teams", None)
    available = list(teams.all()) if teams is not None else []
    if team_id is not None:
        return next((team for team in available if team.pk == team_id), None)
    # 未指定时取第一个律师团队：单团队律所（最常见）不必让前端先选团队。
    return next((team for team in available if getattr(team, "team_type", "") == "lawyer"), None)


def _check_shared_quota(scope: str, owner: dict) -> None:
    limit = MAX_SHARED_SKILLS.get(scope)
    if limit is None:
        return
    queryset = AgentSkill.objects.filter(scope=scope).exclude(status=AgentSkill.Status.ARCHIVED)
    if scope == AgentSkill.Scope.LAW_FIRM:
        queryset = queryset.filter(law_firm_id=owner.get("law_firm_id"))
    else:
        queryset = queryset.filter(team_id=owner["team_id"])
    if queryset.count() >= limit:
        raise SkillQuotaExceeded(f"这一层最多 {limit} 条技能，请先下线不用的")


def _lawyer_or_none(user_id: int | None) -> Any | None:
    if user_id is None:
        return None
    from apps.organization.models import Lawyer

    return Lawyer.objects.select_related("law_firm").prefetch_related("lawyer_teams").filter(pk=user_id).first()


def _scan_findings(payload: dict[str, str]) -> list[dict]:
    """安全闸门的 API 形态（``/skills/validate`` 直接把结果给前端就地提示）。"""
    try:
        from .safety import scan_skill
    except ImportError:  # pragma: no cover - 仅模块缺失期
        return []
    findings = scan_skill(title=payload["title"], description=payload["description"], body=payload["body"])
    return [
        {"code": item.code, "level": item.level, "field": item.field, "message": item.message, "excerpt": item.excerpt}
        for item in findings
    ]


def _builtin_by_key(key: str) -> dict | None:
    """``builtin:<name>`` 或裸内置名 → 内置条目；否则 ``None``。"""
    name = key[len(BUILTIN_PREFIX) :] if key.startswith(BUILTIN_PREFIX) else key
    return {skill["name"]: skill for skill in library.builtin_skills()}.get(name)


def _builtin_enabled(user_id: int, name: str) -> bool:
    return not AgentSkillPreference.objects.filter(
        user_id=user_id, skill_key=f"{BUILTIN_PREFIX}{name}", enabled=False
    ).exists()


def _lock_quota(user_id: int) -> None:
    """事务级咨询锁，把「查配额 + 插入」串行化（必须在 ``transaction.atomic()`` 内调）。

    ``select_for_update`` 在这里没用：配额为 0 时就无行可锁。非 PostgreSQL
    （本地 sqlite）跳过——配额是软上限，并发超出几个不影响正确性。
    """
    if connection.vendor != "postgresql":
        return
    digest = hashlib.sha256(f"agent_skill:quota:{user_id}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _taken_names(user_id: int) -> set[str]:
    """已占用的名字。

    **包含已归档行**：数据库唯一约束本身就含 ``ARCHIVED``，校验口径必须与之一致，
    否则 ``/skills/validate`` 会说「可以用」而 ``POST`` 撞 409。归档技能占名是有
    意的——要复用这个名字就走 ``restore``，否则审计链与偏好会指向两条不同的技能。
    """
    return set(AgentSkill.objects.filter(lawyer_id=user_id).values_list("name", flat=True))


def _quota_used(user_id: int, scope: str) -> int:
    """配额占用（**排除**已归档：下线的不该继续占配额）。"""
    return AgentSkill.objects.filter(lawyer_id=user_id, scope=scope).exclude(status=AgentSkill.Status.ARCHIVED).count()


def _name_conflict(name: str, taken: set[str]) -> str:
    """名字占用的两类冲突走 409（格式/长度问题走 422）：保留名、自己已有同名。"""
    if not name:
        return ""
    if name in validation.reserved_names():
        return f"「{name}」是保留名（内置技能或系统命令），请换一个"
    if name in taken:
        return f"你已有同名技能「{name}」"
    return ""


def _generate_name(taken: set[str]) -> str:
    for _ in range(5):
        name = f"skill-{''.join(secrets.choice(_GENERATED_ALPHABET) for _ in range(6))}"
        if name not in taken and name not in validation.reserved_names():
            return name
    raise SkillConflict("无法生成唯一技能名，请手动指定")


def _unique_name(base: str, taken: set[str]) -> str:
    """``base``、``base-2`` … 取第一个不撞名、不撞保留字的（截断到 64 字）。"""
    for index in range(1, 100):
        suffix = "" if index == 1 else f"-{index}"
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        if candidate not in taken and candidate not in validation.reserved_names():
            return candidate
    raise SkillConflict("无法生成唯一技能名，请手动指定")


def _write_revision(skill: AgentSkill, *, edited_by_id: int) -> AgentSkillRevision:
    """写一条版本快照并返回它（创建与保存都要用返回值接线上指针）。"""
    return AgentSkillRevision.objects.create(
        skill=skill,
        version=skill.version,
        title=skill.title,
        description=skill.description,
        body=skill.body,
        status=skill.status,
        edited_by_id=edited_by_id,
    )


def _drop_partial_tail(page: bytes) -> bytes:
    """切掉末尾不完整的 UTF-8 字符（最多 3 字节）。

    只在分段读取这条路径上用：返回乱码比返回少几个字节糟糕得多——模型会把
    U+FFFD 当成正文照抄，而少几个字节下一段就补上了。
    """
    for cut in range(0, 4):
        tail = page[: len(page) - cut] if cut else page
        try:
            tail.decode("utf-8")
        except UnicodeDecodeError:
            continue
        return tail
    return page
