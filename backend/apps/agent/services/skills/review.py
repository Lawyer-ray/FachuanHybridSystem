"""共享技能的双轨发布生命周期：提审 / 通过 / 驳回 / 下线 / 恢复 / 版本裁剪。

## 双轨的含义（一句话）

**编辑不换线上，发布才换线上。** 任何一次编辑只改工作区字段并写一条新快照，
``status`` 与 ``published_revision`` 都不动；只有 ``approve`` 会把
``published_revision`` 指向新快照。因此审批期间、驳回之后，线上交付的内容
**始终是已批准的那一版**，模型不会因为作者点了保存就突然换指令。

这条规则不是「更稳妥的选择」，而是唯一可行的选择：如果把新正文直接写进
``AgentSkill`` 再置一个 ``status=pending``，那么 ``resolve`` 里一句
``status=ACTIVE`` 就把这条技能**当场下线**——作者改一个错别字，全所 AI 立刻
失去这条指令，而界面上会显示「待审核中」，没人能看出线上已经断了。

## 状态迁移（每一步都要能被审计还原）

| 动作 | status | review_status | published_revision |
|---|---|---|---|
| ``submit`` | 不动 | → ``pending`` | 不动 |
| ``approve`` | → ``active`` | → ``none`` | → 最新快照 |
| ``reject`` | 不动 | → ``rejected`` + note | **纹丝不动** |
| ``archive`` | → ``archived`` | → ``none`` | 保留（审计追溯） |
| ``restore`` | → ``draft`` | → ``none`` | 保留（但不再交付） |
| ``discard_draft`` | 不动 | → ``none`` | 不动（把线上版回填到工作区） |

``restore`` 刻意回 ``draft`` 而不是 ``active``：下线往往意味着「这条指令有问题」，
恢复后直接生效等于让一个有问题的指令绕过一次审批复活。

## 为什么要 ``prune_revisions`` 保护线

版本快照只留最近 ``MAX_REVISIONS`` 条，但 ``published_revision`` 指向的那一条
**永远不许裁**。共享技能长期高频编辑时，「线上生效版」很可能是 20 版之前的
那条（一直没人批新的），裁掉它就是外键置空 → 线上正文瞬间变空 → 静默失效。
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.agent.models import AgentSkill, AgentSkillRevision

from . import permissions
from .constants import MAX_REVISIONS
from .errors import SkillForbidden, SkillInvalid, SkillNotFound
from .render import render_skill_body

logger = logging.getLogger(__name__)


def submit(
    *,
    user_id: int,
    key: str,
    target_scope: str = "",
    note: str = "",
    acknowledged_firm_wide: bool = False,
) -> dict:
    """提审：把当前工作区提交给审批人（**不改线上**）。

    ``target_scope`` 只用于「把个人技能提升为所内技能」这一条路径：传了就先把
    作用域与归属改到目标层，再置 ``pending``。已经在共享层的技能改作用域需要
    管理员，因为那等于改变了谁能审批它。
    """
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if skill.scope == AgentSkill.Scope.LAWYER:
            if not target_scope:
                raise SkillInvalid([{"field": "target_scope", "message": "个人技能提审需要指定目标作用域"}])
            _promote_scope(lawyer, skill, target_scope, acknowledged_firm_wide=acknowledged_firm_wide)
        if not permissions.can_submit(lawyer, skill):
            raise SkillForbidden("你没有提审这条技能的权限")
        hard, soft = _scan(title=skill.title, description=skill.description, body=skill.body)
        if hard:
            raise SkillInvalid([{"field": finding.field, "message": finding.message} for finding in hard])
        _write_workspace_revision(skill, edited_by_id=user_id)
        skill.review_status = AgentSkill.ReviewStatus.PENDING
        skill.review_note = note or ""
        skill.save(update_fields=["review_status", "review_note", "updated_at"])
        revision = skill.revisions.order_by("-version").first()
        logger.info(
            "agent.skill_submitted key=%s scope=%s version=%s soft_findings=%s",
            key,
            skill.scope,
            getattr(revision, "version", 0),
            len(soft),
        )
        return _detail(skill)


def approve(*, user_id: int, key: str, acknowledged_firm_wide: bool = False) -> dict:
    """审批通过：把最新快照提升为线上生效版（唯一会改变线上内容的入口）。"""
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if not permissions.can_review(lawyer, skill):
            raise SkillForbidden("只有本所管理员可以审批共享技能")
        if skill.review_status != AgentSkill.ReviewStatus.PENDING:
            raise SkillInvalid([{"field": "review_status", "message": "这条技能当前没有待审的修改"}])
        if permissions.requires_firm_wide_ack(lawyer, skill) and not acknowledged_firm_wide:
            raise SkillInvalid(
                [{"field": "acknowledged_firm_wide", "message": "全所生效的指令需要先确认影响范围后再发布"}]
            )
        revision = skill.revisions.order_by("-version").first()
        if revision is None:  # pragma: no cover - 有工作区就一定有快照
            raise SkillInvalid([{"field": "body", "message": "没有可发布的版本快照"}])
        # 发布前再扫一次**即将生效的那份快照**，不是工作区：驳回后作者可以继续
        # 增删而没有再提审的窗口，只靠 submit 那一次扫描是不够的。
        hard, _soft = _scan(title=revision.title, description=revision.description, body=revision.body)
        if hard:
            raise SkillInvalid([{"field": finding.field, "message": finding.message} for finding in hard])
        now = timezone.now()
        skill.status = AgentSkill.Status.ACTIVE
        skill.review_status = AgentSkill.ReviewStatus.NONE
        skill.review_note = ""
        skill.published_revision = revision
        skill.reviewed_by_id = user_id
        skill.reviewed_at = now
        skill.activated_at = now
        skill.save(
            update_fields=[
                "status",
                "review_status",
                "review_note",
                "published_revision",
                "reviewed_by",
                "reviewed_at",
                "activated_at",
                "updated_at",
            ]
        )
        logger.info("agent.skill_published key=%s scope=%s version=%s", key, skill.scope, revision.version)
        return _detail(skill)


def reject(*, user_id: int, key: str, note: str) -> dict:
    """驳回：只改修订流状态，**线上旧版毫发无损**。"""
    reason = (note or "").strip()
    if not reason:
        raise SkillInvalid([{"field": "note", "message": "驳回必须写明理由，否则作者只能盲改"}])
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if not permissions.can_review(lawyer, skill):
            raise SkillForbidden("只有本所管理员可以驳回共享技能")
        if skill.review_status != AgentSkill.ReviewStatus.PENDING:
            raise SkillInvalid([{"field": "review_status", "message": "这条技能当前没有待审的修改"}])
        skill.review_status = AgentSkill.ReviewStatus.REJECTED
        skill.review_note = reason
        skill.reviewed_by_id = user_id
        skill.reviewed_at = timezone.now()
        skill.save(update_fields=["review_status", "review_note", "reviewed_by", "reviewed_at", "updated_at"])
        logger.info("agent.skill_rejected key=%s scope=%s", key, skill.scope)
        return _detail(skill)


def archive(*, user_id: int, key: str) -> dict:
    """下线：立刻退出 ``resolve``，但保留 ``published_revision`` 供审计追溯。"""
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if not permissions.can_archive(lawyer, skill):
            raise SkillForbidden("你没有下线这条技能的权限")
        skill.status = AgentSkill.Status.ARCHIVED
        skill.review_status = AgentSkill.ReviewStatus.NONE
        skill.save(update_fields=["status", "review_status", "updated_at"])
        logger.info("agent.skill_archived key=%s scope=%s", key, skill.scope)
        return _detail(skill)


def restore(*, user_id: int, key: str) -> dict:
    """恢复：``archived → draft``，必须重新提审才能再次生效。"""
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if not permissions.can_restore(lawyer, skill):
            raise SkillForbidden("你没有恢复这条技能的权限")
        skill.status = AgentSkill.Status.DRAFT
        skill.review_status = AgentSkill.ReviewStatus.NONE
        skill.save(update_fields=["status", "review_status", "updated_at"])
        logger.info("agent.skill_restored key=%s scope=%s", key, skill.scope)
        return _detail(skill)


def discard_draft(*, user_id: int, key: str) -> dict:
    """放弃工作区：把线上已批准版回填到工作区字段，清掉待审/驳回态。"""
    lawyer = _lawyer(user_id)
    with transaction.atomic():
        skill = _locked_skill(user_id, key)
        if not permissions.can_edit(lawyer, skill):
            raise SkillForbidden("你没有编辑这条技能的权限")
        revision = skill.published_revision
        if revision is None:
            raise SkillInvalid([{"field": "review_status", "message": "这条技能还没有已发布版本，无处回填"}])
        skill.title = revision.title
        skill.description = revision.description
        skill.body = revision.body
        skill.version = revision.version
        skill.review_status = AgentSkill.ReviewStatus.NONE
        skill.review_note = ""
        skill.save(
            update_fields=[
                "title",
                "description",
                "body",
                "version",
                "review_status",
                "review_note",
                "updated_at",
            ]
        )
        return _detail(skill)


def diff_versions(*, user_id: int, key: str, v1: int | None = None, v2: int | None = None) -> dict:
    """两版对比（默认「线上生效版 vs 工作区」）。

    用 ``difflib`` 逐行比：``SequenceMatcher`` 而不是 ``unified_diff``，因为前端
    要的是「哪些行是新增、哪些是删除、哪些没变」的结构，不是一段带 ``@@`` 头
    的文本——后者在中文正文里几乎读不了。
    """
    import difflib

    lawyer = _lawyer(user_id)
    skill = _get_skill(user_id, key)
    if not permissions.can_view(lawyer, skill):
        raise SkillNotFound("技能不存在")

    def _text(version: int | None) -> tuple[str, int]:
        if version is None:
            return skill.body, skill.version
        revision = skill.revisions.filter(version=version).first()
        if revision is None:
            raise SkillInvalid([{"field": "version", "message": f"没有 v{version} 这个版本"}])
        return revision.body, revision.version

    left_version = v1 if v1 is not None else (skill.published_revision.version if skill.published_revision_id else None)
    right_version = v2
    left_text, left_no = _text(left_version)
    right_text, right_no = _text(right_version)

    matcher = difflib.SequenceMatcher(a=left_text.splitlines(), b=right_text.splitlines(), autojunk=False)
    hunks: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            block = left_text.splitlines()[i1:i2]
            hunks.append({"op": "equal", "lines": block})
        elif tag == "replace":
            hunks.append({"op": "del", "lines": left_text.splitlines()[i1:i2]})
            hunks.append({"op": "ins", "lines": right_text.splitlines()[j1:j2]})
        elif tag == "delete":
            hunks.append({"op": "del", "lines": left_text.splitlines()[i1:i2]})
        else:  # insert
            hunks.append({"op": "ins", "lines": right_text.splitlines()[j1:j2]})
    return {"v1": left_no, "v2": right_no, "hunks": hunks}


def prune_revisions(skill: AgentSkill) -> None:
    """裁剪版本快照，但**永远不删 ``published_revision``**（见模块 docstring）。"""
    protected = skill.published_revision_id
    stale = list(skill.revisions.order_by("-version").values_list("id", flat=True)[MAX_REVISIONS:])
    if protected:
        stale = [pk for pk in stale if pk != protected]
    if stale:
        AgentSkillRevision.objects.filter(pk__in=stale).delete()


# ── 内部工具 ──────────────────────────────────────────────────


def _lawyer(user_id: int) -> object:
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.select_related("law_firm").prefetch_related("lawyer_teams").filter(pk=user_id).first()
    if lawyer is None:
        raise SkillNotFound("技能不存在")
    return lawyer


def _get_skill(user_id: int, key: str) -> AgentSkill:
    from .user_skills import _resolve_skill_row

    return _resolve_skill_row(user_id, key)


def _locked_skill(user_id: int, key: str) -> AgentSkill:
    from .user_skills import _resolve_skill_row

    return _resolve_skill_row(user_id, key, for_update=True)


def _promote_scope(lawyer: object, skill: AgentSkill, target_scope: str, *, acknowledged_firm_wide: bool) -> None:
    """把个人技能挂到所内/团队名下（提审第一步）。"""
    if target_scope == AgentSkill.Scope.LAW_FIRM:
        if not permissions.can_create_firm(lawyer):
            raise SkillForbidden("只有本所管理员可以把技能发布到所内")
        if not acknowledged_firm_wide:
            raise SkillInvalid(
                [{"field": "acknowledged_firm_wide", "message": "发布为全所技能前，请确认这条指令在全所范围内成立"}]
            )
        skill.scope = AgentSkill.Scope.LAW_FIRM
        skill.law_firm_id = lawyer.law_firm_id  # type: ignore[attr-defined]
        skill.team = None
        skill.lawyer = None
    elif target_scope == AgentSkill.Scope.TEAM:
        team = getattr(lawyer, "lawyer_teams", None)
        teams = list(team.all()) if team is not None else []
        target = next((item for item in teams if getattr(item, "team_type", "") == "lawyer"), None)
        if target is None or not permissions.can_create_team(lawyer, target):
            raise SkillForbidden("你没有可发布技能的目标团队")
        skill.scope = AgentSkill.Scope.TEAM
        skill.team_id = target.pk
        skill.lawyer = None
        skill.law_firm = None
    else:
        raise SkillInvalid([{"field": "target_scope", "message": "目标作用域只能是 team 或 law_firm"}])


def _write_workspace_revision(skill: AgentSkill, *, edited_by_id: int) -> None:
    """为工作区当前状态写一条快照（提审时补齐 v1 之外的新版本）。"""
    latest = skill.revisions.order_by("-version").first()
    if (
        latest is not None
        and latest.body == skill.body
        and latest.title == skill.title
        and latest.description == skill.description
    ):
        return
    AgentSkillRevision.objects.create(
        skill=skill,
        version=skill.version,
        title=skill.title,
        description=skill.description,
        body=skill.body,
        status=skill.status,
        edited_by_id=edited_by_id,
    )
    prune_revisions(skill)


def _scan(*, title: str, description: str, body: str) -> tuple[list, list]:
    """跑 PII / 注入闸门，返回 ``(hard, soft)``。

    惰性 import + 兜底是刻意的：``safety`` 与生命周期是两个可独立演进的模块，
    但「导入失败就放行」不能成为长期状态，所以一旦模块存在就必须被调用。
    """
    try:
        from .safety import scan_skill
    except ImportError:  # pragma: no cover - 仅模块缺失期
        logger.warning("技能安全闸门模块缺失，本次提审未做 PII 扫描")
        return [], []
    findings = scan_skill(title=title, description=description, body=body)
    hard = [item for item in findings if item.level == "hard"]
    soft = [item for item in findings if item.level == "soft"]
    return hard, soft


def _detail(skill: AgentSkill) -> dict:
    """生命周期动作的回执（管理面字段 + 工作区正文）。"""
    from .user_skills import entry_for_row

    return {
        **entry_for_row(skill),
        "body": skill.body,
        "preview": render_skill_body(scope=str(skill.scope), name=skill.name, title=skill.title, body=skill.body),
    }
