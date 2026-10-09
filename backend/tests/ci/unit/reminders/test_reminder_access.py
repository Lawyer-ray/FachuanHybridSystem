"""全局提醒写权限测试（安全审计 2026Q4 M-1）。

背景：``Reminder`` 的三个关联字段（contract/case/case_log）全空时即「全局
提醒」——团队共享日程。历史上四个写端点只校验关联对象的访问权，全局提醒
没有任何关联对象可校验，于是任何登录用户都能改删全所任何人的全局提醒。

本测试锁定收敛后的口径：
- 全局提醒 → 仅创建人本人与管理员可写
- 关联对象的提醒 → 写权限由关联对象 ACL 决定（本层不重复判定，返回 True）
- created_by 为空的存量全局提醒 → 仅管理员可写（fail-closed）
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.reminders.services.reminder_access import (
    can_write_reminder,
    ensure_can_write_reminder,
    is_admin_user,
)


def _reminder(*, is_global: bool = True, created_by_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        is_global=is_global,
        created_by_id=created_by_id,
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
        reminder = _reminder(created_by_id=7)
        ensure_can_write_reminder(_user(7), reminder)
