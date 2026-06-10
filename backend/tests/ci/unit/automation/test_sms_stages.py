"""Tests for SMS stages: SMSParsingStage, SMSNotifyingStage, SMSRenamingStage, base."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.stages.base import BaseSMSStage
from apps.automation.services.sms.stages.sms_parsing_stage import SMSParsingStage, create_sms_parsing_stage
from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage, create_sms_notifying_stage
from apps.automation.services.sms.stages.sms_renaming_stage import SMSRenamingStage, create_sms_renaming_stage
from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage, create_sms_matching_stage


# ── Factory functions ──


class TestFactoryFunctions:
    def test_create_sms_parsing_stage(self):
        stage = create_sms_parsing_stage()
        assert isinstance(stage, SMSParsingStage)

    def test_create_sms_notifying_stage(self):
        stage = create_sms_notifying_stage()
        assert isinstance(stage, SMSNotifyingStage)

    def test_create_sms_renaming_stage(self):
        stage = create_sms_renaming_stage()
        assert isinstance(stage, SMSRenamingStage)

    def test_create_sms_matching_stage(self):
        stage = create_sms_matching_stage()
        assert isinstance(stage, SMSMatchingStage)


# ── SMSParsingStage ──


class TestSMSParsingStage:
    @pytest.fixture
    def parser_mock(self):
        return MagicMock()

    @pytest.fixture
    def stage(self, parser_mock):
        return SMSParsingStage(parser=parser_mock)

    def test_stage_name(self, stage):
        assert stage.stage_name == "解析"

    def test_can_process_pending(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is True

    def test_can_process_not_pending(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.MATCHING
        assert stage.can_process(sms) is False

    @pytest.mark.django_db
    def test_process_calls_parser(self, stage, parser_mock):
        sms = CourtSMS.objects.create(
            content="test content",
            status=CourtSMSStatus.PENDING,
            received_at="2025-01-01T00:00:00Z",
        )

        parse_result = MagicMock()
        parse_result.sms_type = "judgment"
        parse_result.download_links = ["https://example.com/doc.pdf"]
        parse_result.case_numbers = ["(2025)京0101民初123号"]
        parse_result.party_names = ["张三"]
        parser_mock.parse.return_value = parse_result

        result = stage.process(sms)
        assert result.sms_type == "judgment"
        assert result.download_links == ["https://example.com/doc.pdf"]
        assert result.case_numbers == ["(2025)京0101民初123号"]
        assert result.party_names == ["张三"]
        parser_mock.parse.assert_called_once_with("test content")


# ── SMSNotifyingStage ──


class TestSMSNotifyingStage:
    @pytest.fixture
    def stage(self):
        notification = MagicMock()
        doc_attachment = MagicMock()
        return SMSNotifyingStage(
            notification_service=notification,
            document_attachment_service=doc_attachment,
        )

    def test_stage_name(self, stage):
        assert stage.stage_name == "通知"

    def test_can_process_notifying(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.NOTIFYING
        assert stage.can_process(sms) is True

    def test_can_process_not_notifying(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is False


# ── SMSRenamingStage ──


class TestSMSRenamingStage:
    @pytest.fixture
    def stage(self):
        doc_attachment = MagicMock()
        doc_attachment.get_paths_for_renaming.return_value = []
        case_number_extractor = MagicMock()
        matcher = MagicMock()
        lawyer_service = MagicMock()
        return SMSRenamingStage(
            document_attachment=doc_attachment,
            case_number_extractor=case_number_extractor,
            matcher=matcher,
            lawyer_service=lawyer_service,
        )

    def test_stage_name(self, stage):
        assert stage.stage_name == "重命名"

    def test_can_process_renaming(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.RENAMING
        assert stage.can_process(sms) is True

    def test_can_process_not_renaming(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is False

    @pytest.mark.django_db
    def test_process_no_scraper_task_skips(self, stage):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.RENAMING,
            received_at="2025-01-01T00:00:00Z",
        )
        # scraper_task is None by default
        result = stage.process(sms)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.NOTIFYING


# ── SMSMatchingStage ──


class TestSMSMatchingStage:
    @pytest.fixture
    def stage(self):
        matcher = MagicMock()
        case_number_extractor = MagicMock()
        case_service = MagicMock()
        lawyer_service = MagicMock()
        return SMSMatchingStage(
            matcher=matcher,
            case_number_extractor=case_number_extractor,
            case_service=case_service,
            lawyer_service=lawyer_service,
        )

    def test_stage_name(self, stage):
        assert stage.stage_name == "匹配"

    def test_can_process_matching(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.MATCHING
        assert stage.can_process(sms) is True

    def test_can_process_not_matching(self, stage):
        sms = MagicMock()
        sms.status = CourtSMSStatus.PENDING
        assert stage.can_process(sms) is False

    def test_filter_valid_case_numbers_module_function(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        assert filter_valid_case_numbers(["(2025)京0101民初123号"]) == ["(2025)京0101民初123号"]
        assert filter_valid_case_numbers(["2025年1月1日"]) == []

    @pytest.mark.django_db
    def test_process_with_manual_case(self, stage):
        """Test that manual case assignment works."""
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.MATCHING,
            received_at="2025-01-01T00:00:00Z",
        )
        mock_case = MagicMock()
        mock_case.id = 1

        # Use MagicMock for sms to avoid FK constraint
        mock_sms = MagicMock()
        mock_sms.id = sms.id
        mock_sms.status = CourtSMSStatus.MATCHING
        mock_sms.case = mock_case
        mock_sms.content = "test"
        mock_sms.case_numbers = []
        mock_sms.party_names = []
        mock_sms.error_message = ""
        mock_sms.scraper_task = None
        mock_sms.download_links = []
        mock_sms.save = MagicMock()

        # Mock _create_case_binding
        with patch.object(stage, "_create_case_binding", return_value=True):
            result = stage.process(mock_sms)

        assert result.status == CourtSMSStatus.RENAMING

    @pytest.mark.django_db
    def test_should_wait_no_download_links(self, stage):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.MATCHING,
            received_at="2025-01-01T00:00:00Z",
        )
        sms.party_names = ["张三"]
        sms.download_links = []
        assert stage._should_wait_for_document_download(sms) is False

    @pytest.mark.django_db
    def test_should_wait_with_links_no_task(self, stage):
        sms = CourtSMS.objects.create(
            content="test",
            status=CourtSMSStatus.MATCHING,
            received_at="2025-01-01T00:00:00Z",
        )
        sms.download_links = ["https://example.com"]
        sms.scraper_task = None
        assert stage._should_wait_for_document_download(sms) is False
