"""全局提醒写权限测试（安全审计 2026Q4 M-1）。

背景：``Reminder`` 的三个关联字段（contract/case/case_log）全空时即「全局
提醒」——团队共享日程。历史上四个写端点只校验关联对象的访问权，全局提醒
没有任何关联对象可校验，于是任何登录用户都能改删全所任何人的全局提醒。

本测试锁定收敛后的口径：
- 全局提醒 → 仅创建人本人与管理员可写
- 关联对象的提醒 → 写权限由关联对象 ACL 决定（本层不重复判定，返回 True）
- created_by 为空的存量全局提醒 → 仅管理员可写（fail-closed）

删除单列一档（can_delete_reminder）：不论是否关联案件 / 合同，都只有创建人
与管理员能删——同案同事能勾完成、改时间，但不能删对方建的日程。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.reminders.services.reminder_access import (
    can_delete_reminder,
    can_write_reminder,
    ensure_can_delete_reminder,
    ensure_can_write_reminder,
    is_admin_user,
    reminder_creator_id,
)


def _reminder(
    *, is_global: bool = True, created_by_id: int | None = None, metadata: dict[str, Any] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        is_global=is_global,
        created_by_id=created_by_id,
        metadata=metadata if metadata is not None else {},
        contract_id=None,
        case_id=None,
        case_log_id=None,
    )


def _user(user_id: int, *, is_admin: bool = False, is_superuser: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_admin=is_admin, is_superuser=is_superuser)


class TestIsAdminUser:
    def test_none_is_not_admin(self) -> None:
        assert is_admin_user(None) is False

    def test_is_staff_alone_is_not_admin(self) -> None:
        """is_staff 只是 Django admin 准入标志，不视为系统管理员。"""
        assert is_admin_user(SimpleNamespace(is_staff=True)) is False

    def test_is_admin_flag_counts(self) -> None:
        assert is_admin_user(_user(1, is_admin=True)) is True

    def test_is_superuser_counts(self) -> None:
        assert is_admin_user(_user(1, is_superuser=True)) is True


class TestCanWriteGlobalReminder:
    def test_creator_can_write(self) -> None:
        reminder = _reminder(created_by_id=7)
        assert can_write_reminder(_user(7), reminder) is True

    def test_other_user_cannot_write(self) -> None:
        """他人创建的全局提醒不可改删（M-1 核心）。"""
        reminder = _reminder(created_by_id=7)
        assert can_write_reminder(_user(8), reminder) is False

    def test_admin_can_write_others(self) -> None:
        reminder = _reminder(created_by_id=7)
        assert can_write_reminder(_user(99, is_admin=True), reminder) is True
        assert can_write_reminder(_user(99, is_superuser=True), reminder) is True

    def test_missing_creator_denies_non_admin(self) -> None:
        """存量数据未回填 / 创建人已删 → fail-closed，只放过管理员。"""
        reminder = _reminder(created_by_id=None)
        assert can_write_reminder(_user(7), reminder) is False
        assert can_write_reminder(_user(7, is_admin=True), reminder) is True

    def test_no_user_denies(self) -> None:
        reminder = _reminder(created_by_id=7)
        assert can_write_reminder(None, reminder) is False

    def test_none_reminder_denies(self) -> None:
        assert can_write_reminder(_user(7), None) is False


class TestBoundReminderPassthrough:
    def test_bound_reminder_allows_any_authenticated_user(self) -> None:
        """关联了对象的提醒：写权限由调用方已做的 AccessPolicy 决定。"""
        reminder = _reminder(is_global=False, created_by_id=None)
        assert can_write_reminder(_user(8), reminder) is True


class TestEnsureCanWrite:
    def test_raises_permission_denied_for_non_owner(self) -> None:
        from apps.core.exceptions import PermissionDenied

        reminder = _reminder(created_by_id=7)
        with pytest.raises(PermissionDenied) as exc_info:
            ensure_can_write_reminder(_user(8), reminder)
        assert exc_info.value.code == "REMINDER_NOT_OWNER"

    def test_owner_passes(self) -> None:
        """创建人本人可写（不抛异常即通过，显式固化该契约）。"""
        reminder = _reminder(created_by_id=7)
        assert ensure_can_write_reminder(_user(7), reminder) is None


class TestReminderCreatorId:
    def test_prefers_created_by_fk(self) -> None:
        reminder = _reminder(created_by_id=7, metadata={"created_by_user_id": 8})
        assert reminder_creator_id(reminder) == 7

    def test_falls_back_to_metadata(self) -> None:
        """案件日志等内部路径只写 metadata 不填 FK，须与可见性口径一致。"""
        reminder = _reminder(created_by_id=None, metadata={"created_by_user_id": 8})
        assert reminder_creator_id(reminder) == 8

    def test_metadata_non_int_is_ignored(self) -> None:
        assert reminder_creator_id(_reminder(metadata={"created_by_user_id": "8"})) is None
        assert reminder_creator_id(_reminder(metadata={"created_by_user_id": True})) is None
        assert reminder_creator_id(_reminder(metadata={"created_by_user_id": None})) is None

    def test_missing_everything_is_none(self) -> None:
        assert reminder_creator_id(_reminder()) is None
        assert reminder_creator_id(SimpleNamespace(created_by_id=None, metadata=None)) is None


class TestCanDeleteReminder:
    def test_creator_can_delete_bound_reminder(self) -> None:
        reminder = _reminder(is_global=False, created_by_id=7)
        assert can_delete_reminder(_user(7), reminder) is True

    def test_colleague_cannot_delete_bound_reminder(self) -> None:
        """核心差异：关联了案件的提醒，写放行、删不放行——同案同事也不能删。"""
        reminder = _reminder(is_global=False, created_by_id=7)
        assert can_write_reminder(_user(8), reminder) is True
        assert can_delete_reminder(_user(8), reminder) is False

    def test_other_user_cannot_delete_global_reminder(self) -> None:
        reminder = _reminder(created_by_id=7)
        assert can_delete_reminder(_user(8), reminder) is False

    def test_metadata_creator_can_delete(self) -> None:
        reminder = _reminder(is_global=False, created_by_id=None, metadata={"created_by_user_id": 7})
        assert can_delete_reminder(_user(7), reminder) is True
        assert can_delete_reminder(_user(8), reminder) is False

    def test_admin_can_delete_anything(self) -> None:
        reminder = _reminder(is_global=False, created_by_id=7)
        assert can_delete_reminder(_user(99, is_admin=True), reminder) is True
        assert can_delete_reminder(_user(99, is_superuser=True), reminder) is True

    def test_missing_creator_denies_non_admin(self) -> None:
        """同步 / 导入产生的无主提醒 fail-closed，只有管理员能删。"""
        reminder = _reminder(is_global=False, created_by_id=None)
        assert can_delete_reminder(_user(7), reminder) is False
        assert can_delete_reminder(_user(7, is_admin=True), reminder) is True

    def test_no_user_or_no_reminder_denies(self) -> None:
        assert can_delete_reminder(None, _reminder(created_by_id=7)) is False
        assert can_delete_reminder(_user(7), None) is False


class TestEnsureCanDelete:
    def test_raises_permission_denied_for_non_creator(self) -> None:
        from apps.core.exceptions import PermissionDenied

        reminder = _reminder(is_global=False, created_by_id=7)
        with pytest.raises(PermissionDenied) as exc_info:
            ensure_can_delete_reminder(_user(8), reminder)
        assert exc_info.value.code == "REMINDER_NOT_CREATOR"

    def test_creator_passes(self) -> None:
        reminder = _reminder(is_global=False, created_by_id=7)
        assert ensure_can_delete_reminder(_user(7), reminder) is None
