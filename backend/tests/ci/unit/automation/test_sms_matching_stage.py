"""Coverage tests for sms_matching_stage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.stages.sms_matching_stage import (
    SMSMatchingStage,
    create_sms_matching_stage,
    filter_valid_case_numbers,
)
from apps.automation.models import CourtSMSStatus


class TestFilterValidCaseNumbers:
    def test_filters_date_with_day(self):
        nums = ["2024年3月15号", "（2024）粤01民初1号"]
        result = filter_valid_case_numbers(nums)
        assert result == ["（2024）粤01民初1号"]

    def test_filters_date_with_ri(self):
        nums = ["2024年3月15日", "（2024）粤01民初1号"]
        result = filter_valid_case_numbers(nums)
        assert result == ["（2024）粤01民初1号"]

    def test_keeps_valid_case_numbers(self):
        nums = ["（2024）粤01民初1号", "（2023）京01民终2号"]
        result = filter_valid_case_numbers(nums)
        assert len(result) == 2

    def test_empty_list(self):
        assert filter_valid_case_numbers([]) == []

    def test_all_filtered(self):
        nums = ["2024年1月1日", "2024年12月31号"]
        result = filter_valid_case_numbers(nums)
        assert result == []


class TestSMSMatchingStageInit:
    def test_init_defaults(self):
        stage = SMSMatchingStage()
        assert stage._matcher is None
        assert stage._case_number_extractor is None
        assert stage._case_service is None
        assert stage._lawyer_service is None

    def test_init_with_injection(self):
        m = MagicMock()
        cne = MagicMock()
        cs = MagicMock()
        ls = MagicMock()
        stage = SMSMatchingStage(matcher=m, case_number_extractor=cne, case_service=cs, lawyer_service=ls)
        assert stage._matcher is m
        assert stage._case_number_extractor is cne
        assert stage._case_service is cs
        assert stage._lawyer_service is ls


class TestStageName:
    def test_stage_name(self):
        stage = SMSMatchingStage()
        assert stage.stage_name == "匹配"


class TestCanProcess:
    def test_can_process_matching(self):
        sms = SimpleNamespace(status=CourtSMSStatus.MATCHING)
        stage = SMSMatchingStage()
        assert stage.can_process(sms) is True

    def test_cannot_process_other(self):
        sms = SimpleNamespace(status=CourtSMSStatus.PENDING)
        stage = SMSMatchingStage()
        assert stage.can_process(sms) is False

    def test_cannot_process_failed(self):
        sms = SimpleNamespace(status=CourtSMSStatus.FAILED)
        stage = SMSMatchingStage()
        assert stage.can_process(sms) is False


class TestPropertyLazyLoad:
    def test_matcher_property(self):
        stage = SMSMatchingStage()
        m = MagicMock()
        stage._matcher = m
        assert stage.matcher is m

    def test_case_number_extractor_property(self):
        stage = SMSMatchingStage()
        cne = MagicMock()
        stage._case_number_extractor = cne
        assert stage.case_number_extractor is cne

    def test_case_service_property(self):
        stage = SMSMatchingStage()
        cs = MagicMock()
        stage._case_service = cs
        assert stage.case_service is cs

    def test_lawyer_service_property(self):
        stage = SMSMatchingStage()
        ls = MagicMock()
        stage._lawyer_service = ls
        assert stage.lawyer_service is ls


class TestExtractFromSingleDoc:
    def test_extracts_case_numbers(self):
        stage = SMSMatchingStage()
        stage._case_number_extractor = MagicMock()
        stage._case_number_extractor.extract_from_document.return_value = ["（2024）粤01民初1号"]
        stage._matcher = MagicMock()
        stage._matcher.extract_parties_from_document.return_value = []

        case_numbers: list[str] = []
        party_names: list[str] = []
        changed = stage._extract_from_single_doc("/test/doc.pdf", case_numbers, party_names)
        assert changed is True
        assert "（2024）粤01民初1号" in case_numbers

    def test_extracts_parties(self):
        stage = SMSMatchingStage()
        stage._case_number_extractor = MagicMock()
        stage._case_number_extractor.extract_from_document.return_value = []
        stage._matcher = MagicMock()
        stage._matcher.extract_parties_from_document.return_value = ["张三"]

        case_numbers: list[str] = []
        party_names: list[str] = []
        changed = stage._extract_from_single_doc("/test/doc.pdf", case_numbers, party_names)
        assert changed is True
        assert "张三" in party_names

    def test_no_extraction_when_numbers_exist(self):
        stage = SMSMatchingStage()
        stage._case_number_extractor = MagicMock()
        stage._matcher = MagicMock()
        stage._matcher.extract_parties_from_document.return_value = ["张三"]

        case_numbers: list[str] = ["（2024）粤01民初1号"]
        party_names: list[str] = []
        changed = stage._extract_from_single_doc("/test/doc.pdf", case_numbers, party_names)
        assert changed is True
        # should not call case_number_extractor when already has numbers
        stage._case_number_extractor.extract_from_document.assert_not_called()

    def test_exception_returns_false(self):
        stage = SMSMatchingStage()
        stage._case_number_extractor = MagicMock()
        stage._case_number_extractor.extract_from_document.side_effect = RuntimeError("error")
        stage._matcher = MagicMock()

        case_numbers: list[str] = []
        party_names: list[str] = []
        changed = stage._extract_from_single_doc("/test/doc.pdf", case_numbers, party_names)
        assert changed is False


class TestGetDocumentPathsForExtraction:
    def test_no_scraper_task(self):
        sms = SimpleNamespace(scraper_task=None)
        stage = SMSMatchingStage()
        paths = stage._get_document_paths_for_extraction(sms)
        assert paths == []

    def test_with_scraper_task_documents(self):
        doc = SimpleNamespace(local_file_path="/test/doc.pdf", download_status="success")
        doc_qs = MagicMock()
        doc_qs.filter.return_value.__iter__ = MagicMock(return_value=iter([doc]))
        doc_qs.filter.return_value.exists.return_value = False
        scraper_task = SimpleNamespace(documents=doc_qs, result=None)
        sms = SimpleNamespace(scraper_task=scraper_task)
        stage = SMSMatchingStage()
        with patch("apps.automation.services.sms.stages.sms_matching_stage.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            paths = stage._get_document_paths_for_extraction(sms)
            assert "/test/doc.pdf" in paths

    def test_fallback_to_result_files(self):
        doc_qs = MagicMock()
        doc_qs.filter.return_value.__iter__ = MagicMock(return_value=iter([]))
        doc_qs.filter.return_value.exists.return_value = False
        scraper_task = SimpleNamespace(documents=doc_qs, result={"files": ["/test/file.pdf"]})
        sms = SimpleNamespace(scraper_task=scraper_task)
        stage = SMSMatchingStage()
        with patch("apps.automation.services.sms.stages.sms_matching_stage.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            paths = stage._get_document_paths_for_extraction(sms)
            assert "/test/file.pdf" in paths

    def test_exception_returns_empty(self):
        doc_qs = MagicMock()
        doc_qs.filter.return_value.__iter__ = MagicMock(side_effect=RuntimeError("db error"))
        sms = SimpleNamespace(id=99, scraper_task=SimpleNamespace(documents=doc_qs, result=None))
        stage = SMSMatchingStage()
        paths = stage._get_document_paths_for_extraction(sms)
        assert paths == []


class TestFilterValidCaseNumbersInstance:
    def test_delegates_to_module_function(self):
        stage = SMSMatchingStage()
        result = stage._filter_valid_case_numbers(["2024年1月1日", "（2024）粤01民初1号"])
        assert result == ["（2024）粤01民初1号"]


class TestCreateFactory:
    def test_create_sms_matching_stage(self):
        m = MagicMock()
        cne = MagicMock()
        cs = MagicMock()
        ls = MagicMock()
        stage = create_sms_matching_stage(matcher=m, case_number_extractor=cne, case_service=cs, lawyer_service=ls)
        assert isinstance(stage, SMSMatchingStage)
        assert stage._matcher is m
