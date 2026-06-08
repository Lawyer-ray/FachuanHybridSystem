"""Workbench Admin 测试 - WorkbenchSessionAdmin, WorkbenchMessageAdmin, BatchJobAdmin, BatchJobItemAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.workbench.admin.session_admin import (
    WorkbenchSessionAdmin,
    WorkbenchMessageAdmin,
    BatchJobAdmin,
    BatchJobItemAdmin,
)
from apps.workbench.models import WorkbenchSession, WorkbenchMessage, BatchJob, BatchJobItem

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestWorkbenchSessionAdmin:
    """WorkbenchSessionAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "session_id" in admin_obj.list_display
        assert "title" in admin_obj.list_display
        assert "user" in admin_obj.list_display
        assert "status" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 status"""
        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "status" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 title"""
        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "title" in admin_obj.search_fields


@pytest.mark.django_db
class TestWorkbenchMessageAdmin:
    """WorkbenchMessageAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = WorkbenchMessageAdmin(WorkbenchMessage, AdminSite())
        assert "id" in admin_obj.list_display
        assert "session" in admin_obj.list_display
        assert "role" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 role"""
        admin_obj = WorkbenchMessageAdmin(WorkbenchMessage, AdminSite())
        assert "role" in admin_obj.list_filter


@pytest.mark.django_db
class TestBatchJobAdmin:
    """BatchJobAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = BatchJobAdmin(BatchJob, AdminSite())
        assert "id" in admin_obj.list_display
        assert "session" in admin_obj.list_display
        assert "job_type" in admin_obj.list_display
        assert "status" in admin_obj.list_display
        assert "progress" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 status"""
        admin_obj = BatchJobAdmin(BatchJob, AdminSite())
        assert "status" in admin_obj.list_filter


@pytest.mark.django_db
class TestBatchJobItemAdmin:
    """BatchJobItemAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = BatchJobItemAdmin(BatchJobItem, AdminSite())
        assert "id" in admin_obj.list_display
        assert "job" in admin_obj.list_display
        assert "file_name" in admin_obj.list_display
        assert "status" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 status"""
        admin_obj = BatchJobItemAdmin(BatchJobItem, AdminSite())
        assert "status" in admin_obj.list_filter
