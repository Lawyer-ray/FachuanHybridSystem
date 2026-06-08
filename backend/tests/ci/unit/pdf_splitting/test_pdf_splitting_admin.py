"""PDF Splitting Admin 测试 - PdfSplittingToolAdmin, PdfSplitJobAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.pdf_splitting.admin.pdf_splitting_admin import PdfSplittingToolAdmin, PdfSplitJobAdmin
from apps.pdf_splitting.models import PdfSplitJob, PdfSplittingTool

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestPdfSplitJobAdmin:
    """PdfSplitJobAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PdfSplitJobAdmin(PdfSplitJob, AdminSite())
        assert "id" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含状态相关字段"""
        admin_obj = PdfSplitJobAdmin(PdfSplitJob, AdminSite())
        assert len(admin_obj.list_filter) > 0

    def test_search_fields(self) -> None:
        """search_fields 应存在"""
        admin_obj = PdfSplitJobAdmin(PdfSplitJob, AdminSite())
        assert len(admin_obj.search_fields) > 0
