"""Unit tests for automation.admin.sms.court_sms_admin_base."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCourtSMSAdminBase:
    """测试 CourtSMSAdminBase 基本配置"""

    def _make_admin(self):
        from apps.automation.admin.sms.court_sms_admin_base import CourtSMSAdminBase
        from apps.automation.models import CourtSMS

        return CourtSMSAdminBase(CourtSMS, MagicMock())

    def test_list_display_is_list(self) -> None:
        admin = self._make_admin()
        assert isinstance(admin.list_display, list)
        assert len(admin.list_display) > 0

    def test_list_filter_is_list(self) -> None:
        admin = self._make_admin()
        assert isinstance(admin.list_filter, list)

    def test_search_fields_is_list(self) -> None:
        admin = self._make_admin()
        assert isinstance(admin.search_fields, list)

    def test_autocomplete_fields(self) -> None:
        admin = self._make_admin()
        assert "case" in admin.autocomplete_fields

    def test_list_per_page(self) -> None:
        admin = self._make_admin()
        assert admin.list_per_page == 20

    def test_readonly_fields_contains_id(self) -> None:
        admin = self._make_admin()
        assert "id" in admin.readonly_fields

    def test_readonly_fields_contains_created_at(self) -> None:
        admin = self._make_admin()
        assert "created_at" in admin.readonly_fields
