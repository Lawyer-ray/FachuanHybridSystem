"""Tests for SMSDownloadingStage and related stage infrastructure."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskType
from apps.automation.services.sms.stages.sms_downloading_stage import SMSDownloadingStage, create_sms_downloading_stage


@pytest.fixture
def mock_task_queue():
    return MagicMock()


@pytest.fixture
def mock_execute():
    return MagicMock()


@pytest.fixture
def stage(mock_task_queue, mock_execute):
    return SMSDownloadingStage(task_queue=mock_task_queue, execute_scraper_task=mock_execute)


class TestSMSDownloadingStage:
    def test_stage_name(self, stage):
        assert stage.stage_name == "下载"

    def test_can_process_parsing(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PARSING
        assert stage.can_process(sms) is True

    def test_can_process_not_parsing(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is False

    @pytest.mark.django_db
    def test_process_no_download_links(self, stage):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.PARSING,
            received_at="2025-01-01T00:00:00Z",
        )
        sms.download_links = []
        result = stage.process(sms)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.MATCHING

    @pytest.mark.django_db
    def test_process_with_download_links(self, stage, mock_task_queue):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.PARSING,
            received_at="2025-01-01T00:00:00Z",
        )
        sms.download_links = ["https://example.com/doc.pdf"]
        mock_task_queue.enqueue.return_value = "queue-task-123"

        result = stage.process(sms)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.DOWNLOADING

    def test_create_download_task_no_links(self, stage):
        sms = MagicMock()
        sms.download_links = []
        result = stage._create_download_task(sms)
        assert result is None

    def test_create_download_task_exception(self, stage):
        sms = MagicMock()
        sms.download_links = ["https://example.com/doc.pdf"]
        sms.case = None
        sms.id = 1
        with patch("apps.automation.services.sms.stages.sms_downloading_stage.ScraperTask") as MockTask:
            MockTask.objects.create.side_effect = Exception("DB error")
            result = stage._create_download_task(sms)
        assert result is None
