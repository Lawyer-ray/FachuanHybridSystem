"""Admin 模块测试 - 显示方法和工具函数。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CourtSMSStatus, CourtSMSType


class TestCourtSMSAdminBaseDisplayMethods:
    """测试 CourtSMSAdminBase 的显示方法。"""

    def setup_method(self) -> None:
        from apps.automation.admin.sms.court_sms_admin_base import CourtSMSAdminBase

        self.admin = CourtSMSAdminBase.__new__(CourtSMSAdminBase)

    def _make_sms(self, **kwargs: object) -> SimpleNamespace:
        defaults = {
            "id": 1,
            "status": CourtSMSStatus.PENDING,
            "sms_type": CourtSMSType.DOCUMENT_DELIVERY,
            "content": "测试短信内容",
            "received_at": None,
            "case": None,
            "download_links": [],
            "case_numbers": [],
            "party_names": [],
            "scraper_task": None,
            "case_log_id": None,
            "document_file_paths": [],
            "notification_results": None,
            "feishu_sent_at": None,
            "feishu_error": "",
            "retry_count": 0,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_content_preview_short(self) -> None:
        sms = self._make_sms(content="短内容")
        result = self.admin.content_preview(sms)
        assert result == "短内容"

    def test_content_preview_long(self) -> None:
        sms = self._make_sms(content="x" * 200)
        result = self.admin.content_preview(sms)
        assert len(result) <= 103  # 100 + "..."

    def test_sms_type_display_document_delivery(self) -> None:
        sms = self._make_sms(sms_type=CourtSMSType.DOCUMENT_DELIVERY)
        sms.get_sms_type_display = lambda: "文书送达"
        result = self.admin.sms_type_display(sms)
        assert "文书送达" in result

    def test_sms_type_display_info(self) -> None:
        sms = self._make_sms(sms_type=CourtSMSType.INFO_NOTIFICATION)
        sms.get_sms_type_display = lambda: "信息通知"
        result = self.admin.sms_type_display(sms)
        assert "信息通知" in result

    def test_sms_type_display_filing(self) -> None:
        sms = self._make_sms(sms_type=CourtSMSType.FILING_NOTIFICATION)
        sms.get_sms_type_display = lambda: "立案通知"
        result = self.admin.sms_type_display(sms)
        assert "立案通知" in result

    def test_sms_type_display_none(self) -> None:
        sms = self._make_sms(sms_type=None)
        result = self.admin.sms_type_display(sms)
        assert result == "-"

    def test_has_download_links_true(self) -> None:
        sms = self._make_sms(download_links=["https://example.com"])
        result = self.admin.has_download_links(sms)
        assert "1 个链接" in str(result)

    def test_has_download_links_false(self) -> None:
        sms = self._make_sms(download_links=[])
        result = self.admin.has_download_links(sms)
        assert "无链接" in str(result)

    def test_case_numbers_display_with_numbers(self) -> None:
        sms = self._make_sms(case_numbers=["（2025）粤0604民初1号", "（2025）粤0604民初2号"])
        result = self.admin.case_numbers_display(sms)
        assert "（2025）粤0604民初1号" in str(result)

    def test_case_numbers_display_empty(self) -> None:
        sms = self._make_sms(case_numbers=[])
        result = self.admin.case_numbers_display(sms)
        assert result == "-"

    def test_party_names_display_with_names(self) -> None:
        sms = self._make_sms(party_names=["张三", "李四"])
        result = self.admin.party_names_display(sms)
        assert "张三" in str(result)

    def test_party_names_display_empty(self) -> None:
        sms = self._make_sms(party_names=[])
        result = self.admin.party_names_display(sms)
        assert result == "-"

    def test_download_links_display_with_links(self) -> None:
        sms = self._make_sms(download_links=["https://example.com/1", "https://example.com/2"])
        result = self.admin.download_links_display(sms)
        assert "https://example.com/1" in str(result)

    def test_download_links_display_empty(self) -> None:
        sms = self._make_sms(download_links=[])
        result = self.admin.download_links_display(sms)
        assert result == "-"

    def test_notification_status_no_results(self) -> None:
        sms = self._make_sms(notification_results=None, feishu_sent_at=None, feishu_error="")
        result = self.admin.notification_status(sms)
        assert "未发送" in str(result)

    def test_notification_status_success(self) -> None:
        sms = self._make_sms(
            notification_results={"feishu": {"success": True, "sent_at": "2025-01-01 12:00:00"}},
            feishu_sent_at=None,
        )
        result = self.admin.notification_status(sms)
        assert "通知成功" in str(result)

    def test_notification_status_failure(self) -> None:
        sms = self._make_sms(
            notification_results={"feishu": {"success": False, "error": "发送失败原因"}},
            feishu_sent_at=None,
        )
        result = self.admin.notification_status(sms)
        assert "通知失败" in str(result)

    def test_notification_status_feishu_sent_at_compat(self) -> None:
        """旧字段 feishu_sent_at 兼容。"""
        from datetime import datetime

        sms = self._make_sms(
            notification_results=None,
            feishu_sent_at=datetime(2025, 1, 1, 12, 0),
            feishu_error="",
        )
        result = self.admin.notification_status(sms)
        assert "通知成功" in str(result)

    def test_notification_status_feishu_error_compat(self) -> None:
        """旧字段 feishu_error 兼容。"""
        sms = self._make_sms(notification_results=None, feishu_sent_at=None, feishu_error="发送失败")
        result = self.admin.notification_status(sms)
        assert "通知失败" in str(result)

    def test_notification_details_success(self) -> None:
        sms = self._make_sms(
            notification_results={"feishu": {"success": True, "sent_at": "2025-01-01 12:00:00", "chat_id": "C001"}}
        )
        result = self.admin.notification_details(sms)
        assert "成功" in result
        assert "C001" in result

    def test_notification_details_failure(self) -> None:
        sms = self._make_sms(
            notification_results={"feishu": {"success": False, "error": "连接超时"}}
        )
        result = self.admin.notification_details(sms)
        assert "失败" in result
        assert "连接超时" in result

    def test_notification_details_no_results(self) -> None:
        sms = self._make_sms(notification_results=None, feishu_sent_at=None, feishu_error="")
        result = self.admin.notification_details(sms)
        assert result == "未发送"

    def test_retry_button_with_id(self) -> None:
        sms = self._make_sms(id=123)
        with patch("apps.automation.admin.sms.court_sms_admin_base.reverse", return_value="/admin/retry/123/"):
            result = self.admin.retry_button(sms)
            assert "重新处理" in str(result)

    def test_retry_button_without_id(self) -> None:
        sms = self._make_sms(id=None)
        result = self.admin.retry_button(sms)
        assert result == "-"

    def test_scraper_task_link_with_task(self) -> None:
        task = SimpleNamespace(id=1)
        task.get_status_display = lambda: "已完成"
        sms = self._make_sms(scraper_task=task)
        with patch("apps.automation.admin.sms.court_sms_admin_base.reverse", return_value="/admin/task/1/"):
            result = self.admin.scraper_task_link(sms)
            assert "任务" in str(result)

    def test_scraper_task_link_without_task(self) -> None:
        sms = self._make_sms(scraper_task=None)
        result = self.admin.scraper_task_link(sms)
        assert result == "-"
