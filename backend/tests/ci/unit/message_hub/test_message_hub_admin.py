"""Message Hub Admin 测试 - InboxMessageAdmin, MessageSourceAdmin"""

from __future__ import annotations

from typing import Any

import pytest

try:
    from plugins import has_message_hub_plugin
    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

if _HAS_MH:
    from plugins.message_hub.admin.inbox_message_admin import InboxMessageAdmin

if _HAS_MH:
    from plugins.message_hub.admin.message_source_admin import MessageSourceAdmin

from apps.message_hub.models import InboxMessage, MessageSource
from apps.organization.models import AccountCredential, LawFirm, Lawyer

User = get_user_model()

def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request

def _create_message_source() -> tuple[AccountCredential, MessageSource]:
    """创建消息来源测试数据"""
    firm = LawFirm.objects.create(name="消息测试律所")
    lawyer = Lawyer.objects.create_user(username="msg_lawyer", real_name="消息律师", law_firm=firm)
    cred = AccountCredential.objects.create(
        lawyer=lawyer, site_name="imap_site", account="msg_account", password="test_pass"  # allowlist secret
    )
    source = MessageSource.objects.create(
        credential=cred,
        source_type="imap",
        display_name="测试邮箱",
        is_enabled=True,
        poll_interval_minutes=30,
        sync_since=timezone.now(),
    )
    return cred, source

@pytest.mark.django_db
class TestInboxMessageAdmin:
    """InboxMessageAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        assert "subject_display" in admin_obj.list_display
        assert "source_badge" in admin_obj.list_display
        assert "received_at" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 source"""
        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        assert "source" in admin_obj.list_select_related

    def test_search_fields(self) -> None:
        """search_fields 包含 subject"""
        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        assert "subject" in admin_obj.search_fields

    def test_ordering(self) -> None:
        """排序应按 received_at 降序"""
        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        assert admin_obj.ordering == ["-received_at"]

    def test_get_queryset_no_n_plus_1(self) -> None:
        """get_queryset 应使用 select_related 避免 N+1"""
        _, source = _create_message_source()
        InboxMessage.objects.create(
            source=source,
            message_id="msg_001",
            subject="测试邮件",
            sender="test@example.com",
            received_at=timezone.now(),
        )

        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].source.display_name == "测试邮箱"

@pytest.mark.django_db
class TestMessageSourceAdmin:
    """MessageSourceAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = MessageSourceAdmin(MessageSource, AdminSite())
        assert "display_name" in admin_obj.list_display
        assert "is_enabled" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 应存在"""
        admin_obj = MessageSourceAdmin(MessageSource, AdminSite())
        assert len(admin_obj.list_filter) > 0
