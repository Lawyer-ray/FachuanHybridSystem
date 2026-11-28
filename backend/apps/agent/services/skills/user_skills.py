"""个人技能 CRUD（P0 只做 ``scope=lawyer``）。

DB 写是权威，落盘只是 pi 的注入缓存：**先提交事务，``transaction.on_commit``
里再写盘**；落盘失败只 ``logger.warning``，不回滚 DB——下一轮
``enabled_skill_paths`` 会跳过缺失目录，``skills_reconcile`` 可重建。

``key`` 是身份（``builtin:<name>`` / ``skill:<uuid>``），``name`` 只是命令名与
目录名；别人的技能按「不存在」处理（404）。``PUT`` 带 ``version`` 做乐观锁，
每次保存写一条 ``AgentSkillRevision``，只留最近 ``MAX_REVISIONS`` 版。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import string
import uuid

from django.db import IntegrityError, connection, transaction

from apps.agent.models import AgentSkill, AgentSkillPreference, AgentSkillRevision

from . import library, resolve, store, validation
from .constants import BUILTIN_PREFIX, MAX_REVISIONS, MAX_TITLE, MAX_USER_SKILLS, USER_PREFIX
from .errors import (
    SkillConflict,
    SkillForbidden,
    SkillInvalid,
    SkillNotFound,
    SkillQuotaExceeded,
)
from .render import render_skill_md

logger = logging.getLogger(__name__)

_GENERATED_ALPHABET = string.digits + string.ascii_lowercase


def list_for_user(user_id: int) -> list[dict]:
    """可见技能清单（内置 + 个人，含禁用项与 ``shadowed``）。"""
    return resolve.visible_skills(user_id)


def quota_for_user(user_id: int) -> dict[str, int]:
    """个人技能配额占用（``used`` 不含已归档行）。"""
    return {"max_skills": MAX_USER_SKILLS, "used": _quota_used(user_id)}


def get_detail(user_id: int, key: str) -> dict:
    """技能详情（含 ``body``）；内置看文件，个人看数据库。"""
    builtin = _builtin_by_key(key)
    if builtin is not None:
        body = library.read_body(builtin["name"])
        return {**builtin, "enabled": _builtin_enabled(user_id, builtin["name"]), "body": body}
    skill = _own_skill(user_id, key)
    return {**_entry(skill), "body": skill.body}


def validate_form(*, user_id: int, name: str | None, title: str, description: str, body: str) -> dict:
    """``POST /skills/validate``：字段级错误 + 渲染预览（AI 实际读到的内容）。"""
    payload = validation.normalize_payload(name=name, title=title, description=description, body=body)
    errors = validation.validate_payload(payload, require_name=False, taken_names=_taken_names(user_id))
    preview = render_skill_md(payload["name"] or "skill-preview", payload["description"], payload["body"])
    return {"ok": not errors, "errors": errors, "preview": preview}


def create_skill(
    *, user_id: int, name: str | None, title: str, description: str, body: str, source: str = "manual"
) -> dict:
    """新建个人技能（``name`` 可省略 → 后端生成 ``skill-<6位base36>``）。"""
    payload = validation.normalize_payload(name=name, title=title, description=description, body=body)
    taken = _taken_names(user_id)
    conflict = _name_conflict(payload["name"], taken)
    if conflict:
        raise SkillConflict(conflict)
    errors = validation.validate_payload(payload, require_name=False)
    if errors:
        raise SkillInvalid(errors)
    if not payload["name"]:
        payload["name"] = _generate_name(taken)
    with transaction.atomic():
        # 配额必须与插入同一事务、并串行化：否则两个并发创建都读到 used=19，
        # 双双落库（20 上限被破）。手法同 doc_workspace 的 _acquire_seq_lock。
        _lock_quota(user_id)
        if _quota_used(user_id) >= MAX_USER_SKILLS:
            raise SkillQuotaExceeded(f"个人技能最多 {MAX_USER_SKILLS} 个，请先删除不用的技能")
        try:
            skill = AgentSkill.objects.create(
                scope=AgentSkill.Scope.LAWYER,
                lawyer_id=user_id,
                name=payload["name"],
                title=payload["title"],
                description=payload["description"],
                body=payload["body"],
                status=AgentSkill.Status.ACTIVE,
                enabled=True,
                source=source,
                version=1,
                created_by_id=user_id,
            )
        except IntegrityError as exc:
            raise SkillConflict(f"技能名「{payload['name']}」已被占用") from exc
        _write_revision(skill, edited_by_id=user_id)
        _prune_revisions(skill)
        _schedule_write(skill)
    return {**_entry(skill), "body": skill.body}


def update_skill(*, user_id: int, key: str, title: str, description: str, body: str, expected_version: int) -> dict:
    """按 ``expected_version`` 乐观锁更新；``name`` 不可改（改名 = 断偏好与审计）。"""
    payload = validation.normalize_payload(name=None, title=title, description=description, body=body)
    errors = validation.validate_payload(payload, require_name=False)
    if errors:
        raise SkillInvalid(errors)
    with transaction.atomic():
        skill = _own_skill(user_id, key, for_update=True)
        if skill.version != expected_version:
            raise SkillConflict(f"技能已被修改（当前 v{skill.version}），请刷新后重试")
        skill.title = payload["title"]
        skill.description = payload["description"]
        skill.body = payload["body"]
        skill.version += 1
        skill.save(update_fields=["title", "description", "body", "version", "updated_at"])
        _write_revision(skill, edited_by_id=user_id)
        _prune_revisions(skill)
        _schedule_write(skill)
    return {**_entry(skill), "body": skill.body}


def delete_skill(*, user_id: int, key: str) -> None:
    """删除个人技能（内置 → 403；别人的 → 404）。"""
    if _builtin_by_key(key) is not None:
        raise SkillForbidden("内置技能不能删除，只能停用")
    with transaction.atomic():
        skill = _own_skill(user_id, key)
        if skill.lawyer_id is None:  # pragma: no cover - CHECK 约束保证 lawyer 作用域必有归属
            raise SkillNotFound("技能不存在")
        lawyer_id, name = int(skill.lawyer_id), skill.name
        skill.delete()
        transaction.on_commit(lambda: _remove_from_disk(lawyer_id, name))


def set_enabled(*, user_id: int, key: str, enabled: bool) -> dict:
    """启停：内置写偏好行（缺省启用），个人写 ``enabled`` 字段。"""
    builtin = _builtin_by_key(key)
    if builtin is not None:
        AgentSkillPreference.objects.update_or_create(
            user_id=user_id, skill_key=builtin["key"], defaults={"enabled": enabled}
        )
        return {"key": builtin["key"], "enabled": enabled}
    with transaction.atomic():
        skill = _own_skill(user_id, key, for_update=True)
        skill.enabled = enabled
        skill.save(update_fields=["enabled", "updated_at"])
        if enabled:
            _schedule_write(skill)
        else:
            _schedule_remove(skill)
        normalized = f"{USER_PREFIX}{skill.pk}"
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


def _entry(skill: AgentSkill) -> dict:
    return {
        "key": f"{USER_PREFIX}{skill.pk}",
        "name": skill.name,
        "title": skill.title,
        "description": skill.description,
        "enabled": skill.enabled,
        "source": "user",
        "scope": skill.scope,
        "editable": True,
        "version": skill.version,
        "shadowed": [],
    }


def _builtin_by_key(key: str) -> dict | None:
    """``builtin:<name>`` 或裸内置名 → 内置条目；否则 ``None``（兼容旧前端/测试）。"""
    name = key[len(BUILTIN_PREFIX) :] if key.startswith(BUILTIN_PREFIX) else key
    return {skill["name"]: skill for skill in library.builtin_skills()}.get(name)


def _builtin_enabled(user_id: int, name: str) -> bool:
    return not AgentSkillPreference.objects.filter(
        user_id=user_id, skill_key=f"{BUILTIN_PREFIX}{name}", enabled=False
    ).exists()


def _own_skill(user_id: int, key: str, *, for_update: bool = False) -> AgentSkill:
    """按 ``skill:<uuid>`` 取自己的技能；其它一律 404（不泄漏别人的存在性）。"""
    if not key.startswith(USER_PREFIX):
        raise SkillNotFound("技能不存在")
    try:
        skill_id = uuid.UUID(key[len(USER_PREFIX) :])
    except ValueError:
        raise SkillNotFound("技能不存在") from None
    queryset = AgentSkill.objects.filter(pk=skill_id, lawyer_id=user_id, scope=AgentSkill.Scope.LAWYER)
    skill = (queryset.select_for_update() if for_update else queryset).first()
    if skill is None:
        raise SkillNotFound("技能不存在")
    return skill


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
    rows = AgentSkill.objects.filter(lawyer_id=user_id).exclude(status=AgentSkill.Status.ARCHIVED)
    return set(rows.values_list("name", flat=True))


def _quota_used(user_id: int) -> int:
    return AgentSkill.objects.filter(lawyer_id=user_id).exclude(status=AgentSkill.Status.ARCHIVED).count()


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


def _write_revision(skill: AgentSkill, *, edited_by_id: int) -> None:
    AgentSkillRevision.objects.create(
        skill=skill,
        version=skill.version,
        title=skill.title,
        description=skill.description,
        body=skill.body,
        status=skill.status,
        edited_by_id=edited_by_id,
    )


def _prune_revisions(skill: AgentSkill) -> None:
    stale = list(skill.revisions.order_by("-version").values_list("id", flat=True)[MAX_REVISIONS:])
    if stale:
        AgentSkillRevision.objects.filter(pk__in=stale).delete()


def _schedule_write(skill: AgentSkill) -> None:
    """事务提交后再物化（回调只带原始值，不把模型实例带出事务）。"""
    if skill.lawyer_id is None:  # pragma: no cover - CHECK 约束保证 lawyer 作用域必有归属
        return
    lawyer_id, name = int(skill.lawyer_id), skill.name
    transaction.on_commit(lambda: _write_to_disk(lawyer_id, name, skill.description, skill.body))


def _schedule_remove(skill: AgentSkill) -> None:
    if skill.lawyer_id is None:  # pragma: no cover - CHECK 约束保证 lawyer 作用域必有归属
        return
    lawyer_id, name = int(skill.lawyer_id), skill.name
    transaction.on_commit(lambda: _remove_from_disk(lawyer_id, name))


def _write_to_disk(lawyer_id: int, name: str, description: str, body: str) -> None:
    """落盘失败只告警（DB 已提交，回滚不了也不该回滚）。"""
    try:
        store.write_content(lawyer_id, name, description, body)
    except (OSError, ValueError):
        logger.warning("个人技能物化失败（下一轮跳过注入，可运行 skills_reconcile 修复）: %s/%s", lawyer_id, name, exc_info=True)


def _remove_from_disk(lawyer_id: int, name: str) -> None:
    try:
        store.remove_skill(lawyer_id, name)
    except (OSError, ValueError):
        logger.warning("个人技能目录删除失败（可运行 skills_reconcile --prune）: %s/%s", lawyer_id, name, exc_info=True)
