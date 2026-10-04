"""GSXT 报告邮件轮询任务的终止条件测试。

修复背景：check_gsxt_report_email 此前未收到邮件就无限续期 schedule（60 秒/次），
永久轮询。现在轮询超过上限（约 30 分钟）后标记 FAILED 并写明「报告邮件未到达」，
不再续期。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

from apps.automation.models.gsxt_report import GsxtReportStatus
from apps.automation.tasks.gsxt_tasks import REPORT_EMAIL_POLL_TIMEOUT, check_gsxt_report_email


def _make_task(*, created_at, status=GsxtReportStatus.WAITING_EMAIL) -> MagicMock:
    task = MagicMock()
    task.status = status
    task.created_at = created_at
    return task


class TestCheckGsxtReportEmailPollLimit:
    @patch("apps.automation.tasks.gsxt_tasks.django_apps")
    @patch("apps.core.tasking.ScheduleQueryService")
    @patch("apps.automation.services.gsxt.gsxt_email_service._fetch_report_attachment")
    @patch("apps.automation.models.gsxt_report.GsxtReportTask")
    def test_poll_timeout_marks_failed_and_stops_rescheduling(
        self, MockTask, MockFetch, MockSched, MockApps
    ) -> None:
        """超过轮询上限：标 FAILED、写明原因、不再续期 schedule。"""
        task = _make_task(created_at=timezone.now() - REPORT_EMAIL_POLL_TIMEOUT - timedelta(seconds=1))
        MockTask.objects.select_related.return_value.get.return_value = task
        MockFetch.return_value = None  # 未收到邮件
        MockApps.get_model.return_value.objects.get.return_value = MagicMock(account="a", password="b")

        check_gsxt_report_email(1, "测试公司")

        assert task.status == GsxtReportStatus.FAILED
        assert "报告邮件未到达" in task.error_message
        task.save.assert_called_once_with(update_fields=["status", "error_message"])
        MockSched.return_value.create_once_schedule.assert_not_called()

    @patch("apps.automation.tasks.gsxt_tasks.django_apps")
    @patch("apps.core.tasking.ScheduleQueryService")
    @patch("apps.automation.services.gsxt.gsxt_email_service._fetch_report_attachment")
    @patch("apps.automation.models.gsxt_report.GsxtReportTask")
    def test_within_limit_reschedules(self, MockTask, MockFetch, MockSched, MockApps) -> None:
        """未超上限：保持 WAITING_EMAIL 并续期 60 秒重试。"""
        task = _make_task(created_at=timezone.now() - timedelta(seconds=60))
        MockTask.objects.select_related.return_value.get.return_value = task
        MockFetch.return_value = None
        MockApps.get_model.return_value.objects.get.return_value = MagicMock(account="a", password="b")

        check_gsxt_report_email(2, "测试公司")

        assert task.status == GsxtReportStatus.WAITING_EMAIL
        MockSched.return_value.create_once_schedule.assert_called_once()

    @patch("apps.automation.tasks.gsxt_tasks.django_apps")
    @patch("apps.core.tasking.ScheduleQueryService")
    @patch("apps.automation.services.gsxt.gsxt_email_service._fetch_report_attachment")
    @patch("apps.automation.models.gsxt_report.GsxtReportTask")
    def test_terminal_status_exits_early(self, MockTask, MockFetch, MockSched, MockApps) -> None:
        """任务已终态（非 WAITING_EMAIL）：直接返回，不查邮件也不续期。"""
        task = _make_task(created_at=timezone.now(), status=GsxtReportStatus.SUCCESS)
        MockTask.objects.select_related.return_value.get.return_value = task

        check_gsxt_report_email(3, "测试公司")

        MockFetch.assert_not_called()
        MockSched.return_value.create_once_schedule.assert_not_called()
