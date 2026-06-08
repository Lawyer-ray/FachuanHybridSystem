"""Batch Printing Admin 测试 - BatchPrintJobAdmin, PrintPresetSnapshotAdmin, PrintKeywordRuleAdmin"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.batch_printing.admin.batch_printing_admin import (
    BatchPrintJobAdmin,
    PrintPresetSnapshotAdmin,
    PrintKeywordRuleAdmin,
)
from apps.batch_printing.models import BatchPrintJob, PrintPresetSnapshot, PrintKeywordRule

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestBatchPrintJobAdmin:
    """BatchPrintJobAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = BatchPrintJobAdmin(BatchPrintJob, AdminSite())
        assert "id" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 应存在"""
        admin_obj = BatchPrintJobAdmin(BatchPrintJob, AdminSite())
        assert len(admin_obj.list_filter) > 0

    def test_search_fields(self) -> None:
        """search_fields 应存在"""
        admin_obj = BatchPrintJobAdmin(BatchPrintJob, AdminSite())
        assert len(admin_obj.search_fields) > 0


@pytest.mark.django_db
class TestPrintPresetSnapshotAdmin:
    """PrintPresetSnapshotAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PrintPresetSnapshotAdmin(PrintPresetSnapshot, AdminSite())
        assert "printer_name" in admin_obj.list_display
        assert "preset_name" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含 printer_name"""
        admin_obj = PrintPresetSnapshotAdmin(PrintPresetSnapshot, AdminSite())
        assert "printer_name" in admin_obj.search_fields

    def test_str_representation(self) -> None:
        """__str__ 应返回正确的格式"""
        snapshot = PrintPresetSnapshot.objects.create(
            printer_name="HP LaserJet",
            preset_name="默认",
            last_synced_at=timezone.now(),
        )
        assert str(snapshot) == "HP LaserJet / 默认"


@pytest.mark.django_db
class TestPrintKeywordRuleAdmin:
    """PrintKeywordRuleAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PrintKeywordRuleAdmin(PrintKeywordRule, AdminSite())
        assert "keyword" in admin_obj.list_display
        assert "priority" in admin_obj.list_display
        assert "enabled" in admin_obj.list_display

    def test_str_representation(self) -> None:
        """__str__ 应返回正确的格式"""
        snapshot = PrintPresetSnapshot.objects.create(
            printer_name="Canon",
            preset_name="高质量",
            last_synced_at=timezone.now(),
        )
        rule = PrintKeywordRule.objects.create(
            keyword="起诉状",
            priority=100,
            enabled=True,
            printer_name="Canon",
            preset_snapshot=snapshot,
        )
        assert str(rule) == "起诉状 -> Canon/高质量"
