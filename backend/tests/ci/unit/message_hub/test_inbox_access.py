"""inbox_access.py 单元测试：收件箱消息/来源的可见性收敛（安全审计 2026Q4 IDOR）。

聚焦纯判定逻辑：is_admin_user / can_view_message / can_view_source 与
QuerySet 过滤（visible_messages_qs / visible_sources_qs）。
历史缺口：list_messages / list_sources 及各附件端点无任何归属过滤，
任意登录用户可遍历 message_id 批量拉取全库材料。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.message_hub.services.inbox_access import (
    can_view_message,
    can_view_source,
    is_admin_user,
    visible_messages_qs,
    visible_sources_qs,
)


def _user(uid: int = 1, **flags: bool) -> SimpleNamespace:
    return SimpleNamespace(id=uid, is_authenticated=True, **flags)


def _source(credential_lawyer_id: int | None = None) -> SimpleNamespace:
    credential = None if credential_lawyer_id is None else SimpleNamespace(lawyer_id=credential_lawyer_id)
    return SimpleNamespace(pk=1, credential=credential)


def _message(*, uploaded_by_id: int | None = None, source: Any = None) -> SimpleNamespace:
    return SimpleNamespace(pk=1, uploaded_by_id=uploaded_by_id, source=source)


class TestIsAdminUser:
    def test_none_user_is_not_admin(self) -> None:
        assert is_admin_user(None) is False

    def test_plain_user_is_not_admin(self) -> None:
        assert is_admin_user(_user()) is False

    def test_superuser_is_admin(self) -> None:
        assert is_admin_user(_user(is_superuser=True)) is True

    def test_is_admin_flag_is_admin(self) -> None:
        assert is_admin_user(_user(is_admin=True)) is True

    def test_is_staff_alone_is_not_admin(self) -> None:
        """is_staff 仅是 Django admin 准入标志，不视为系统管理员。"""
        assert is_admin_user(_user(is_staff=True)) is False


class TestCanViewMessage:
    def test_own_uploaded_message_visible(self) -> None:
        user = _user(uid=7)
        assert can_view_message(user, _message(uploaded_by_id=7)) is True

    def test_other_users_upload_not_visible(self) -> None:
        user = _user(uid=7)
        assert can_view_message(user, _message(uploaded_by_id=8)) is False

    def test_external_message_visible_to_source_credential_owner(self) -> None:
        user = _user(uid=7)
        msg = _message(uploaded_by_id=None, source=_source(credential_lawyer_id=7))
        assert can_view_message(user, msg) is True

    def test_external_message_hidden_from_other_lawyer(self) -> None:
        user = _user(uid=7)
        msg = _message(uploaded_by_id=None, source=_source(credential_lawyer_id=9))
        assert can_view_message(user, msg) is False

    def test_credentialless_source_message_only_admin(self) -> None:
        """无凭证来源的历史数据 fail-closed：仅管理员可见。"""
        msg = _message(uploaded_by_id=None, source=_source(credential_lawyer_id=None))
        assert can_view_message(_user(uid=7), msg) is False
        assert can_view_message(_user(uid=7, is_superuser=True), msg) is True

    def test_admin_sees_everything(self) -> None:
        admin = _user(uid=1, is_superuser=True)
        assert can_view_message(admin, _message(uploaded_by_id=999)) is True
        assert can_view_message(admin, _message(uploaded_by_id=None, source=_source(credential_lawyer_id=999))) is True

    def test_anonymous_user_sees_nothing(self) -> None:
        assert can_view_message(None, _message(uploaded_by_id=1)) is False


class TestCanViewSource:
    def test_credential_owner_can_view(self) -> None:
        assert can_view_source(_user(uid=5), _source(credential_lawyer_id=5)) is True

    def test_other_lawyer_cannot_view(self) -> None:
        assert can_view_source(_user(uid=5), _source(credential_lawyer_id=6)) is False

    def test_credentialless_source_only_admin(self) -> None:
        src = _source(credential_lawyer_id=None)
        assert can_view_source(_user(uid=5), src) is False
        assert can_view_source(_user(uid=5, is_admin=True), src) is True


class TestVisibleQuerysets:
    """QuerySet 过滤行为（django_db 下验证实际 SQL 语义）。"""

    @pytest.mark.django_db
    def test_anonymous_gets_empty_queryset(self, django_assert_num_queries: Any = None) -> None:
        assert visible_messages_qs(None).count() == 0
        assert visible_sources_qs(None).count() == 0

    @pytest.mark.django_db
    def test_scoped_querysets_are_lazy_and_filterable(self) -> None:
        """返回的是 QuerySet（可继续 filter/切片），不是 list。"""
        from django.db.models import QuerySet

        user = _user(uid=42)
        assert isinstance(visible_messages_qs(user), QuerySet)
        assert isinstance(visible_sources_qs(user), QuerySet)
        # 组合过滤不报错（list_messages 会继续叠加 source_id/search 等条件）
        assert visible_messages_qs(user).filter(source_id=1)[:5] is not None
