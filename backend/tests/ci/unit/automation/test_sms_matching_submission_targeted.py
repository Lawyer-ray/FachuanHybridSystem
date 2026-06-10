"""Targeted tests for SMSMatchingStage and SMSSubmissionService."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskType


# ── SMSMatchingStage pure function tests ──────────────────────────


class TestFilterValidCaseNumbers:
    """Test the filter_valid_case_numbers pure function."""

    def test_filters_date_format(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers

        result = filter_valid_case_numbers(["2024年1月1日", "（2024）京0101民初1234号"])
        assert result == ["（2024）京0101民初1234号"]

    def test_filters_year_month_day_号(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers

        result = filter_valid_case_numbers(["2024年6月15号", "正常案号"])
        assert result == ["正常案号"]

    def test_keeps_valid_numbers(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers

        nums = ["（2024）京0101民初1234号", "（2023）沪0115民初5678号"]
        result = filter_valid_case_numbers(nums)
        assert result == nums

    def test_empty_list(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers

        assert filter_valid_case_numbers([]) == []

    def test_all_filtered(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers

        result = filter_valid_case_numbers(["2024年1月1日", "2023年6月30日"])
        assert result == []


# ── SMSSubmissionService tests ────────────────────────────────────


@pytest.fixture
def sms_submission():
    from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

    return SMSSubmissionService(
        case_service=MagicMock(),
        lawyer_service=MagicMock(),
    )


@pytest.fixture
def court_sms(db):
    return CourtSMS.objects.create(
        content="测试短信内容",
        received_at=timezone.now(),
        status=CourtSMSStatus.PENDING,
    )


@pytest.mark.django_db
class TestSMSSubmissionServiceSubmit:
    def test_empty_content_raises(self, sms_submission):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="短信内容不能为空"):
            sms_submission.submit_sms("")

    def test_whitespace_content_raises(self, sms_submission):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="短信内容不能为空"):
            sms_submission.submit_sms("   ")

    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_creates_sms(self, mock_submit, sms_submission):
        mock_submit.return_value = "task-1"
        sms = sms_submission.submit_sms("法院通知：（2024）京0101民初1234号案件已受理")
        assert sms.pk is not None
        assert sms.status == CourtSMSStatus.PENDING
        assert sms.content == "法院通知：（2024）京0101民初1234号案件已受理"

    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_custom_received_at(self, mock_submit, sms_submission):
        mock_submit.return_value = "task-2"
        now = timezone.now()
        sms = sms_submission.submit_sms("内容", received_at=now)
        assert sms.received_at == now


@pytest.mark.django_db
class TestSMSSubmissionServiceRetry:
    def test_not_found_raises(self, sms_submission):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            sms_submission.retry_processing(999999)

    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_resets_status(self, mock_submit, sms_submission, court_sms):
        mock_submit.return_value = "task-3"
        court_sms.status = CourtSMSStatus.FAILED
        court_sms.error_message = "错误"
        court_sms.retry_count = 1
        court_sms.save()

        result = sms_submission.retry_processing(court_sms.id)
        assert result.status == CourtSMSStatus.PENDING
        assert result.error_message is None
        assert result.retry_count == 2


@pytest.mark.django_db
class TestSMSSubmissionServiceAssignCase:
    def test_not_found_sms_raises(self, sms_submission):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            sms_submission.assign_case(999999, 1)

    def test_not_found_case_raises(self, sms_submission, court_sms):
        from apps.core.exceptions import NotFoundError

        sms_submission.case_service.get_case_by_id_internal.return_value = None
        with pytest.raises(NotFoundError, match="案件不存在"):
            sms_submission.assign_case(court_sms.id, 999999)


@pytest.mark.django_db
class TestFilterValidCaseNumbersInService:
    def test_filters_dates(self, sms_submission):
        result = sms_submission._filter_valid_case_numbers(["2024年1月1日", "正常案号"])
        assert result == ["正常案号"]


# ── SMSMatchingStage class tests ──────────────────────────────────


@pytest.mark.django_db
class TestSMSMatchingStage:
    def _make_stage(self):
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage

        return SMSMatchingStage(
            matcher=MagicMock(),
            case_number_extractor=MagicMock(),
            case_service=MagicMock(),
            lawyer_service=MagicMock(),
        )

    def test_can_process_matching(self):
        stage = self._make_stage()
        sms = MagicMock()
        sms.status = CourtSMSStatus.MATCHING
        assert stage.can_process(sms) is True

    def test_can_process_other_status(self):
        stage = self._make_stage()
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is False

    def test_stage_name(self):
        stage = self._make_stage()
        assert stage.stage_name == "匹配"

    def test_filter_valid_case_numbers(self):
        stage = self._make_stage()
        result = stage._filter_valid_case_numbers(["2024年1月1日", "正常案号"])
        assert "正常案号" in result
        assert "2024年1月1日" not in result


@pytest.mark.django_db
class TestSMSMatchingStageShouldWaitForDownload:
    def test_no_scraper_task_returns_false(self):
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage

        stage = SMSMatchingStage()
        sms = MagicMock()
        sms.party_names = []
        sms.download_links = []
        sms.scraper_task = None
        assert stage._should_wait_for_document_download(sms) is False

    def test_has_party_names_returns_false(self):
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage

        stage = SMSMatchingStage()
        sms = MagicMock()
        sms.party_names = ["张某"]
        sms.download_links = ["https://example.com"]
        sms.scraper_task = MagicMock()
        assert stage._should_wait_for_document_download(sms) is False

    def test_no_download_links_returns_false(self):
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage

        stage = SMSMatchingStage()
        sms = MagicMock()
        sms.party_names = []
        sms.download_links = []
        sms.scraper_task = MagicMock()
        assert stage._should_wait_for_document_download(sms) is False
