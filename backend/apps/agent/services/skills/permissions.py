"""技能权限：谁能看、谁能改、谁能提审、谁能审批、谁能下线。

## 为什么单独成一个模块而不是写在 service 里

技能权限会在四个地方被问到：API 的每个写端点、审批面板、解析层（决定
``list_visible_skills`` 要不要返回草稿）、以及前端（靠服务端下发的
``can_*`` 字段控制按钮显隐）。**前端必须只看服务端算出来的布尔值**——
前端自己判 ``is_admin`` 就意味着有人能在浏览器里改一个 flag 绕过审批。

## 三条不能用直觉写的约束

1. **只认 ``lawyer.is_admin``**。它既不是 ``is_superuser`` 也不是 ``is_staff``：
   本仓库里三者可以互相独立（``organization/models/lawyer.py:74``），技能权限
   与记忆口径保持一致（记忆也用 ``is_admin``）。
2. **``lawyer.law_firm`` 可以为空**。没有律所的律师不参与任何团队/所内动作，
   而且查询层**绝不能**把 ``law_firm_id=None`` 当成一个「律所」去匹配——
   那会让所有无律所律师共享同一个隐式租户。
3. **不要求双人会签**。生产环境存在只有 0/1 名管理员的律所
   （``services/memory/curation.py:102-104`` 实证），强制 ``author != reviewer``
   会让这类律所永久死锁在「没人能批」。代价是管理员可以自审自发，所以自审时
   必须显式勾选「已确认全所生效」（``acknowledged_firm_wide``），把这一次
   点击留在审计里。

## 与记忆模块的一处刻意差异

**严禁**照抄 ``services/memory/scopes.py:can_curate_scope``：那段代码在
``scope == TEAM`` 时只要 ``is_admin`` 就放行，既不校验团队所属律所也不校验
团队类型，且未知 scope 默认返回 ``True``。技能是**行为指令**，一次越权发布
会让外所的 AI 按错流程走且当事人无从察觉，所以这里每条分支都必须显式给出
归属证据，未知作用域一律 fail-closed。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _firm_id(lawyer: Any) -> int | None:
    """律师所属律所 id（``None`` = 无律所，所有团队/所内动作 fail-closed）。"""
    value = getattr(lawyer, "law_firm_id", None)
    return int(value) if value is not None else None


def _is_admin(lawyer: Any) -> bool:
    return bool(getattr(lawyer, "is_admin", False))


def _team_ids(lawyer: Any) -> set[int]:
    """律师所属的**律师团队** id 集合。

    只取 ``team_type == "lawyer"``：业务团队（``biz``）是案件分工用的，不是
    人员组织单元，把它们也算进技能作用域会让「谁能改团队技能」变得不可解释。
    """
    try:
        teams = lawyer.lawyer_teams.all()
    except (AttributeError, ValueError):  # 未保存的实例 / 无 M2M
        return set()
    return {int(team.pk) for team in teams if getattr(team, "team_type", "") == "lawyer"}


def same_firm(lawyer: Any, skill_row: Any) -> bool:
    """技能归属的律所/团队是否与律师同所（跨所隔离的唯一判据）。"""
    firm_id = _firm_id(lawyer)
    if firm_id is None:
        return False
    scope = getattr(skill_row, "scope", "")
    if scope == "law_firm":
        return getattr(skill_row, "law_firm_id", None) == firm_id
    if scope == "team":
        team = getattr(skill_row, "team", None)
        if team is None:
            return False
        # 团队的律所必须显式等于律师的律所：两个都可能为 None 的字段用 == 比，
        # None == None 会误判成「同所」，所以要先挡掉 None。
        team_firm = getattr(team, "law_firm_id", None)
        return team_firm is not None and team_firm == firm_id and getattr(team, "team_type", "") == "lawyer"
    return False


def is_author(lawyer: Any, skill_row: Any) -> bool:
    """是否这条技能的创建人（共享技能里作者能编辑自己的草稿）。"""
    lawyer_id = getattr(lawyer, "pk", None)
    if lawyer_id is None:
        return False
    created_by = getattr(skill_row, "created_by_id", None)
    if created_by is not None and created_by == lawyer_id:
        return True
    return getattr(skill_row, "lawyer_id", None) == lawyer_id


def can_view(lawyer: Any, skill_row: Any) -> bool:
    """能否看到这条技能（含草稿/待审）。

    已生效的共享技能对本所全员可见；未生效的只对作者与审批人可见——否则
    「待审草稿」会变成全所可读的半成品，比不发布更糟。
    """
    if lawyer is None or skill_row is None:
        return False
    scope = str(getattr(skill_row, "scope", ""))
    if scope == "lawyer":
        return getattr(skill_row, "lawyer_id", None) == getattr(lawyer, "pk", None)
    if scope in ("team", "law_firm"):
        if not same_firm(lawyer, skill_row):
            return False
        if getattr(skill_row, "status", "") == "active":
            return True
        return is_author(lawyer, skill_row) or can_review(lawyer, skill_row)
    return False


def can_edit(lawyer: Any, skill_row: Any) -> bool:
    """能否编辑正文。个人=本人；团队=同所团队成员；所内=同所全员（提交仍需审批）。"""
    if lawyer is None or skill_row is None:
        return False
    scope = str(getattr(skill_row, "scope", ""))
    if scope == "lawyer":
        return getattr(skill_row, "lawyer_id", None) == getattr(lawyer, "pk", None)
    if scope == "team":
        team = getattr(skill_row, "team", None)
        if team is None or not same_firm(lawyer, skill_row):
            return False
        return int(getattr(team, "pk", 0) or 0) in _team_ids(lawyer) or _is_admin(lawyer)
    if scope == "law_firm":
        # 所内技能的任何本所律师都可以改「工作区」——改完必走审批，
        # 所以放开编辑不等于放开生效（真正生效的闸门在 review.approve）。
        return _firm_id(lawyer) is not None and same_firm(lawyer, skill_row)
    return False


def can_submit(lawyer: Any, skill_row: Any) -> bool:
    """能否提审（把当前工作区提交给审批人）。

    个人技能不需要提审（``review.submit`` 会直接拒绝 ``scope=lawyer``），
    所以这里对个人恒 ``False``。
    """
    if lawyer is None or skill_row is None:
        return False
    scope = str(getattr(skill_row, "scope", ""))
    if scope not in ("team", "law_firm"):
        return False
    if getattr(skill_row, "status", "") == "archived":
        return False
    if getattr(skill_row, "review_status", "none") == "pending":
        return False
    return can_edit(lawyer, skill_row)


def can_review(lawyer: Any, skill_row: Any) -> bool:
    """能否审批（通过/驳回）。只有本所管理员，且技能必须在自己的所内。"""
    if lawyer is None or skill_row is None:
        return False
    if not _is_admin(lawyer):
        return False
    scope = str(getattr(skill_row, "scope", ""))
    if scope not in ("team", "law_firm"):
        return False
    return same_firm(lawyer, skill_row)


def can_archive(lawyer: Any, skill_row: Any) -> bool:
    """能否下线。个人=本人；共享=审批人（管理员）。"""
    if lawyer is None or skill_row is None:
        return False
    if str(getattr(skill_row, "scope", "")) == "lawyer":
        return getattr(skill_row, "lawyer_id", None) == getattr(lawyer, "pk", None)
    return can_review(lawyer, skill_row)


def can_restore(lawyer: Any, skill_row: Any) -> bool:
    """能否把已下线的技能恢复成草稿（恢复后必须重走审批，不绕过）。"""
    if lawyer is None or skill_row is None:
        return False
    if getattr(skill_row, "status", "") != "archived":
        return False
    if str(getattr(skill_row, "scope", "")) == "lawyer":
        return getattr(skill_row, "lawyer_id", None) == getattr(lawyer, "pk", None)
    return can_review(lawyer, skill_row)


def can_create_firm(lawyer: Any) -> bool:
    """能否新建所内技能（只有本所管理员）。"""
    if lawyer is None or not _is_admin(lawyer):
        return False
    return _firm_id(lawyer) is not None


def can_create_team(lawyer: Any, team: Any) -> bool:
    """能否在某个团队里新建技能（团队成员或本所管理员，且团队必须同所且为律师团队）。"""
    if lawyer is None or team is None:
        return False
    firm_id = _firm_id(lawyer)
    if firm_id is None:
        return False
    if getattr(team, "law_firm_id", None) != firm_id:
        return False
    if getattr(team, "team_type", "") != "lawyer":
        return False
    return int(getattr(team, "pk", 0) or 0) in _team_ids(lawyer) or _is_admin(lawyer)


def can_promote(lawyer: Any, skill_row: Any) -> bool:
    """能否把这条技能**提到共享层**（个人 → 所内 / 团队）。

    单独成函数而不是复用 ``can_create_firm``：后者回答的是「你能不能在所内建一条
    新技能」，而这里还要看这条技能自身的状态——已在共享层的、待审中的、已下线的
    都不该出现「提升」入口。前端只渲染服务端算出来的布尔，所以口径必须精确。
    """
    if lawyer is None or skill_row is None:
        return False
    if str(getattr(skill_row, "scope", "")) != "lawyer":
        return False
    if getattr(skill_row, "status", "") == "archived":
        return False
    if getattr(skill_row, "review_status", "none") == "pending":
        return False
    return bool(promotable_scopes(lawyer))


def promotable_scopes(lawyer: Any) -> list[str]:
    """这条律师可以把技能提到哪些作用域（顺序即前端展示顺序）。"""
    if lawyer is None or _firm_id(lawyer) is None:
        return []
    scopes: list[str] = []
    if _team_ids(lawyer) or _is_admin(lawyer):
        scopes.append("team")
    if _is_admin(lawyer):
        scopes.append("law_firm")
    return scopes


def requires_firm_wide_ack(lawyer: Any, skill_row: Any) -> bool:
    """审批时是否需要勾选「已确认全所生效」。

    只对**管理员自审自发**要求：普通成员提审、管理员审别人时不需要额外确认
    （那一步的点击本身已经是确认）。没有这条区分，每个管理员批自己的技能都要
    多点一次，很快会变成盲点。
    """
    if not can_review(lawyer, skill_row):
        return False
    return is_author(lawyer, skill_row)


def capability_flags(lawyer: Any, skill_row: Any | None = None) -> dict[str, bool]:
    """一次性算出条目上要随 API 下发的 ``can_*`` 字段（前端只读这些）。"""
    if skill_row is None:
        # 内置技能没有数据库行：五个动作全 False（它能做的只有「复制为我的」）。
        # 字段集必须与有行时**完全一致**——少一个就会让按 §2 声明的 response schema
        # 直接 422/500，而症状是「清单接口挂了」，很难联想到是这里少了一行。
        return {
            "can_edit": False,
            "can_submit": False,
            "can_review": False,
            "can_archive": False,
            "can_restore": False,
            "can_promote": False,
        }
    return {
        "can_edit": can_edit(lawyer, skill_row),
        "can_submit": can_submit(lawyer, skill_row),
        "can_review": can_review(lawyer, skill_row),
        "can_archive": can_archive(lawyer, skill_row),
        "can_restore": can_restore(lawyer, skill_row),
        "can_promote": can_promote(lawyer, skill_row),
    }
