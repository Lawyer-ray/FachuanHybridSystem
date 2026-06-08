"""Automation Admin 测试 - CourtSMSAdmin, ScraperTaskAdmin, CourtTokenAdmin"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
from apps.automation.admin.scraper.scraper_task_admin import ScraperTaskAdmin
from apps.automation.admin.token.token_admin import CourtTokenAdmin
from apps.automation.models import CourtSMS, ScraperTask, CourtToken

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestScraperTaskAdmin:
    """ScraperTaskAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        assert "id" in admin_obj.list_display
        assert "task_type" in admin_obj.list_display
        assert "priority" in admin_obj.list_display
        assert "status_colored" in admin_obj.list_display
        assert "created_at" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case"""
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        assert "case" in admin_obj.list_select_related

    def test_get_model_perms_hidden(self) -> None:
        """get_model_perms 应返回空字典（隐藏后台入口）"""
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        perms = admin_obj.get_model_perms(_make_request())
        assert perms == {}

    def test_status_colored(self) -> None:
        """status_colored 应返回带颜色的状态"""
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url="https://example.com"
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.status_colored(task)
        assert "等待中" in result
        assert "color" in result

    def test_url_short_truncation(self) -> None:
        """url_short 应截断长 URL"""
        long_url = "https://example.com/" + "a" * 100
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url=long_url
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.url_short(task)
        assert len(result) <= 53  # 50 + "..."

    def test_url_short_no_truncation(self) -> None:
        """url_short 不应截断短 URL"""
        short_url = "https://example.com"
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url=short_url
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.url_short(task)
        assert result == short_url

    def test_retry_info(self) -> None:
        """retry_info 应显示重试信息"""
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url="https://example.com",
            retry_count=2, max_retries=3
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.retry_info(task)
        assert "2" in result
        assert "3" in result

    def test_retry_info_zero(self) -> None:
        """retry_info 零重试时应显示 0"""
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url="https://example.com",
            retry_count=0, max_retries=3
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.retry_info(task)
        assert "0" in result

    def test_duration_with_times(self) -> None:
        """duration 应计算耗时"""
        now = timezone.now()
        task = ScraperTask.objects.create(
            task_type="court_document", status="success", url="https://example.com",
            started_at=now - timedelta(seconds=30), finished_at=now
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.duration(task)
        assert "30.0秒" in result

    def test_duration_without_times(self) -> None:
        """duration 无时间时应返回破折号"""
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url="https://example.com"
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.duration(task)
        assert result == "-"

    def test_result_display_empty(self) -> None:
        """result_display 无结果时应返回破折号"""
        task = ScraperTask.objects.create(
            task_type="court_document", status="pending", url="https://example.com"
        )
        admin_obj = ScraperTaskAdmin(ScraperTask, AdminSite())
        result = admin_obj.result_display(task)
        assert result == "-"


@pytest.mark.django_db
class TestCourtTokenAdmin:
    """CourtTokenAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        assert "id" in admin_obj.list_display
        assert "site_name_display" in admin_obj.list_display
        assert "account" in admin_obj.list_display
        assert "token_preview" in admin_obj.list_display
        assert "status_display" in admin_obj.list_display

    def test_get_model_perms_hidden(self) -> None:
        """get_model_perms 应返回空字典（隐藏后台入口）"""
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        perms = admin_obj.get_model_perms(_make_request())
        assert perms == {}

    def test_has_add_permission_disabled(self) -> None:
        """禁用添加"""
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        assert admin_obj.has_add_permission(_make_request()) is False

    def test_has_change_permission_disabled(self) -> None:
        """禁用修改"""
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        assert admin_obj.has_change_permission(_make_request()) is False

    def test_site_name_display(self) -> None:
        """site_name_display 应返回可读站点名称"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account", token="test_placeholder_1",
            expires_at=timezone.now() + timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.site_name_display(token)
        assert "人民法院在线服务网" in result

    def test_token_preview_short(self) -> None:
        """token_preview 应显示前20个字符"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token="a" * 50, expires_at=timezone.now() + timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.token_preview(token)
        assert "..." in result
        assert len(result) <= 23  # 20 + "..."

    def test_token_preview_short_token(self) -> None:
        """token_preview 短 token 不应截断"""
        short_token = "short_token"
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token=short_token, expires_at=timezone.now() + timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.token_preview(token)
        assert result == short_token

    def test_status_display_valid(self) -> None:
        """status_display 应显示有效状态"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token="test_placeholder_2", expires_at=timezone.now() + timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.status_display(token)
        assert "有效" in result

    def test_status_display_expired(self) -> None:
        """status_display 应显示过期状态"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token="test_placeholder_3", expires_at=timezone.now() - timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.status_display(token)
        assert "已过期" in result

    def test_remaining_time_valid(self) -> None:
        """remaining_time 应显示剩余时间"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token="test_placeholder_4", expires_at=timezone.now() + timedelta(hours=2)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.remaining_time(token)
        assert "小时" in result or "分钟" in result

    def test_remaining_time_expired(self) -> None:
        """remaining_time 过期时应显示已过期"""
        token = CourtToken.objects.create(
            site_name="court_zxfw", account="test_account",
            token="test_placeholder_5", expires_at=timezone.now() - timedelta(hours=1)
        )
        admin_obj = CourtTokenAdmin(CourtToken, AdminSite())
        result = admin_obj.remaining_time(token)
        assert "已过期" in result
