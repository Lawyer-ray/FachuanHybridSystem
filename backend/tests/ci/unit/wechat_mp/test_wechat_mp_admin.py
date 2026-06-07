"""WeChat MP Admin 测试 - WeChatAccountAdmin, PublishTaskAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.wechat_mp.admin import WeChatAccountAdmin, PublishTaskAdmin
from apps.wechat_mp.models import WeChatAccount, PublishTask

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestWeChatAccountAdmin:
    """WeChatAccountAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = WeChatAccountAdmin(WeChatAccount, AdminSite())
        assert "name" in admin_obj.list_display
        assert "mp_url" in admin_obj.list_display
        assert "is_active" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 is_active"""
        admin_obj = WeChatAccountAdmin(WeChatAccount, AdminSite())
        assert "is_active" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 name"""
        admin_obj = WeChatAccountAdmin(WeChatAccount, AdminSite())
        assert "name" in admin_obj.search_fields

    def test_str_representation(self) -> None:
        """__str__ 应返回账号名称"""
        account = WeChatAccount.objects.create(name="测试公众号")
        assert str(account) == "测试公众号"

    def test_save_model_auto_set_created_by(self) -> None:
        """save_model 应自动设置 created_by"""
        user = User.objects.create_user(username="wechat_user", is_staff=True)
        account = WeChatAccount(name="自动创建人测试")

        request = _make_request()
        request.user = user

        admin_obj = WeChatAccountAdmin(WeChatAccount, AdminSite())
        admin_obj.save_model(request, account, None, False)
        assert account.created_by == user


@pytest.mark.django_db
class TestPublishTaskAdmin:
    """PublishTaskAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PublishTaskAdmin(PublishTask, AdminSite())
        assert "title" in admin_obj.list_display
        assert "account" in admin_obj.list_display
        assert "status" in admin_obj.list_display
        assert "created_at" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 account"""
        admin_obj = PublishTaskAdmin(PublishTask, AdminSite())
        assert "account" in admin_obj.list_select_related

    def test_list_filter(self) -> None:
        """list_filter 包含 status"""
        admin_obj = PublishTaskAdmin(PublishTask, AdminSite())
        assert "status" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 title"""
        admin_obj = PublishTaskAdmin(PublishTask, AdminSite())
        assert "title" in admin_obj.search_fields
