"""Tests for SMS-related services: SMSSubmissionService, filter_valid_case_numbers, SMSMatchingStage helpers."""
from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
from apps.core.exceptions import NotFoundError, ValidationException


# ── filter_valid_case_numbers (pure function) ──


class TestFilterValidCaseNumbers:
    def test_empty_list(self):
        assert filter_valid_case_numbers([]) == []

    def test_valid_case_number_kept(self):
        assert filter_valid_case_numbers(["(2025)京0101民初123号"]) == ["(2025)京0101民初123号"]

    def test_date_format_filtered(self):
        result = filter_valid_case_numbers(["2025年1月15日"])
        assert result == []

    def test_date_with_hao_filtered(self):
        result = filter_valid_case_numbers(["2025年1月15号"])
        assert result == []

    def test_mixed_valid_and_invalid(self):
        result = filter_valid_case_numbers([
            "(2025)京0101民初123号",
            "2025年1月15日",
            "普通文本",
        ])
        assert result == ["(2025)京0101民初123号", "普通文本"]

    def test_non_date_content_kept(self):
        result = filter_valid_case_numbers(["案件说明", "补充材料"])
        assert result == ["案件说明", "补充材料"]

    def test_date_in_middle_of_text(self):
        # "年"/"月"/"日" present but not matching date pattern at start
        result = filter_valid_case_numbers(["本年度1月15日提交"])
        # This has 年, 月, 日 so it should be filtered
        assert result == []


# ── SMSSubmissionService ──


class TestSMSSubmissionService:
    @pytest.fixture
    def svc(self):
        return SMSSubmissionService(case_service=MagicMock(), lawyer_service=MagicMock())

    # ── submit_sms ──

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_submit_sms_success(self, mock_submit, svc):
        mock_submit.return_value = "task-123"
        sms = svc.submit_sms("测试短信内容")
        assert sms.id is not None
        assert sms.status == CourtSMSStatus.PENDING
        assert sms.content == "测试短信内容"

    @pytest.mark.django_db
    def test_submit_sms_empty_content(self, svc):
        with pytest.raises(ValidationException, match="短信内容不能为空"):
            svc.submit_sms("")

    @pytest.mark.django_db
    def test_submit_sms_whitespace_only(self, svc):
        with pytest.raises(ValidationException, match="短信内容不能为空"):
            svc.submit_sms("   ")

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_submit_sms_with_received_at(self, mock_submit, svc):
        mock_submit.return_value = "task-123"
        now = timezone.now()
        sms = svc.submit_sms("content", received_at=now)
        assert sms.received_at == now

    # ── assign_case ──

    @pytest.mark.django_db
    def test_assign_case_sms_not_found(self, svc):
        with pytest.raises(NotFoundError, match="短信记录不存在"):
            svc.assign_case(999999, 1)

    @pytest.mark.django_db
    def test_assign_case_case_not_found(self, svc):
        sms = CourtSMS.objects.create(
            content="test", status=CourtSMSStatus.PENDING, received_at=timezone.now()
        )
        svc.case_service.get_case_by_id_internal.return_value = None
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.assign_case(sms.id, 999)

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_assign_case_binds_successfully(self, mock_submit, svc):
        """Test that assign_case calls _create_case_binding and sets status to RENAMING."""
        sms = CourtSMS.objects.create(
            content="test", status=CourtSMSStatus.PENDING, received_at=timezone.now()
        )
        mock_case = MagicMock()
        mock_case.id = 42
        svc.case_service.get_case_by_id_internal.return_value = mock_case

        # Mock _create_case_binding and CourtSMS.objects.get to avoid FK issues
        with patch.object(svc, "_create_case_binding", return_value=True) as mock_bind, \
             patch("apps.automation.models.CourtSMS.objects.get", return_value=sms):
            # Patch save to avoid FK constraint
            with patch.object(type(sms), "save"):
                result = svc.assign_case(sms.id, 42)

        assert result.status == CourtSMSStatus.RENAMING
        mock_bind.assert_called_once_with(sms)

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_assign_case_binding_fails(self, mock_submit, svc):
        """Test that assign_case sets FAILED when binding fails."""
        sms = CourtSMS.objects.create(
            content="test", status=CourtSMSStatus.PENDING, received_at=timezone.now()
        )
        mock_case = MagicMock()
        mock_case.id = 42
        svc.case_service.get_case_by_id_internal.return_value = mock_case

        with patch.object(svc, "_create_case_binding", return_value=False), \
             patch("apps.automation.models.CourtSMS.objects.get", return_value=sms):
            with patch.object(type(sms), "save"):
                result = svc.assign_case(sms.id, 42)

        assert result.status == CourtSMSStatus.FAILED

    # ── retry_processing ──

    @pytest.mark.django_db
    def test_retry_processing_sms_not_found(self, svc):
        with pytest.raises(NotFoundError, match="短信记录不存在"):
            svc.retry_processing(999999)

    @pytest.mark.django_db
    @patch("apps.automation.services.sms.submission.sms_submission_service.submit_task")
    def test_retry_processing_success(self, mock_submit, svc):
        mock_submit.return_value = "task-456"
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.FAILED,
            received_at=timezone.now(),
            retry_count=0,
        )
        result = svc.retry_processing(sms.id)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.PENDING
        assert result.retry_count == 1
        assert result.error_message is None

    # ── _filter_valid_case_numbers ──

    def test_filter_valid_case_numbers(self, svc):
        assert svc._filter_valid_case_numbers(["2025年1月1日"]) == []
        assert svc._filter_valid_case_numbers(["(2025)京0101民初123号"]) == ["(2025)京0101民初123号"]

    # ── _add_case_numbers_to_case ──

    def test_add_case_numbers_no_case(self, svc):
        sms = MagicMock()
        sms.case = None
        sms.case_numbers = ["123"]
        svc._add_case_numbers_to_case(sms)  # should not raise

    def test_add_case_numbers_no_numbers(self, svc):
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case_numbers = []
        svc._add_case_numbers_to_case(sms)  # should not raise

    # ── _create_case_binding ──

    def test_create_case_binding_no_case(self, svc):
        sms = MagicMock()
        sms.case = None
        assert svc._create_case_binding(sms) is False
