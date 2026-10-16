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


class TestMultiLineDisplayColumns:
    """多行列（案号/当事人）换行回归：Django 6.1 起 format_html_join 的 sep 也过
    conditional_escape，字面 "<br>" 分隔符会被转义成 &lt;br&gt; 字面文本
    （2026-10-12 列表页「提取的当事人」换行失效根因），分隔符必须 mark_safe。
    """

    def _make_admin(self):
        from apps.automation.admin.sms.court_sms_admin_base import CourtSMSAdminBase
        from apps.automation.models import CourtSMS

        return CourtSMSAdminBase(CourtSMS, MagicMock())

    def _make_sms(self, db):
        from django.utils import timezone

        from apps.automation.models import CourtSMS

        return CourtSMS.objects.create(
            content="【测试法院】<b>张三</b>你好",
            received_at=timezone.now(),
            case_numbers=["（2026）粤0604民初1号", "（2026）粤0604民初2号"],
            party_names=["甲方公司", "<script>乙方</script>"],
        )

    def test_party_names_line_break_is_raw_br(self, db):
        admin = self._make_admin()
        sms = self._make_sms(db)

        html = str(admin.party_names_display(sms))

        assert "<br>" in html
        assert "&lt;br&gt;" not in html
        # 当事人名仍需转义（用户可控内容）
        assert "&lt;script&gt;" in html

    def test_case_numbers_line_break_is_raw_br(self, db):
        admin = self._make_admin()
        sms = self._make_sms(db)

        html = str(admin.case_numbers_display(sms))

        assert html.count("<br>") == 1
        assert "&lt;br&gt;" not in html
