"""
Tests for apps.automation.services.document_delivery — 文书送达数据类和匹配逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentRecord,
    DocumentQueryResult,
    DocumentProcessResult,
)


# ============================================================
# DocumentRecord 测试
# ============================================================


class TestDocumentRecord:
    """DocumentRecord 数据类测试"""

    def test_from_api_response_full(self) -> None:
        data = {
            "ah": "（2025）粤0604民初41257号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-12-10 16:25:37",
            "fymc": "佛山市禅城区人民法院",
            "ahdm": "YGD0604",
            "fybh": "440604",
            "ssdrxm": "张三",
            "wsmc": "受理案件通知书",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初41257号"
        assert record.sdbh == "SD001"
        assert record.fssj == "2025-12-10 16:25:37"
        assert record.fymc == "佛山市禅城区人民法院"

    def test_from_api_response_defaults(self) -> None:
        record = DocumentRecord.from_api_response({})
        assert record.ah == ""
        assert record.sdbh == ""
        assert record.fssj == ""
        assert record.fymc == ""

    def test_parse_fssj_valid(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="2025-12-10 16:25:37", fymc="")
        dt = record.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 10
        assert dt.hour == 16
        assert dt.minute == 25

    def test_parse_fssj_empty(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid_format(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="not-a-date", fymc="")
        assert record.parse_fssj() is None

    def test_to_dict(self) -> None:
        record = DocumentRecord(ah="test", sdbh="SD1", ajzybh="AJ1", fssj="2025-01-01", fymc="法院")
        d = record.to_dict()
        assert d["ah"] == "test"
        assert d["sdbh"] == "SD1"
        assert d["fymc"] == "法院"


# ============================================================
# DocumentDetail 测试
# ============================================================


class TestDocumentDetail:
    def test_from_api_response(self) -> None:
        data = {"c_sdbh": "SD1", "c_wsmc": "判决书", "c_wjgs": "pdf", "wjlj": "https://example.com/file.pdf"}
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "SD1"
        assert detail.c_wsmc == "判决书"
        assert detail.wjlj == "https://example.com/file.pdf"

    def test_to_dict(self) -> None:
        detail = DocumentDetail(c_sdbh="SD1", c_wsmc="判决书", c_wjgs="pdf", wjlj="url")
        d = detail.to_dict()
        assert d["c_sdbh"] == "SD1"
        assert d["c_wsmc"] == "判决书"


# ============================================================
# DocumentListResponse 测试
# ============================================================


class TestDocumentListResponse:
    def test_from_api_response(self) -> None:
        data = {
            "code": 200,
            "data": {
                "total": 2,
                "data": [
                    {"ah": "案号1", "sdbh": "SD1", "ajzybh": "AJ1", "fssj": "", "fymc": "法院1"},
                    {"ah": "案号2", "sdbh": "SD2", "ajzybh": "AJ2", "fssj": "", "fymc": "法院2"},
                ],
            },
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2
        assert resp.documents[0].ah == "案号1"

    def test_from_api_response_empty(self) -> None:
        resp = DocumentListResponse.from_api_response({})
        assert resp.total == 0
        assert resp.documents == []

    def test_to_dict(self) -> None:
        resp = DocumentListResponse(
            total=1,
            documents=[DocumentRecord(ah="test", sdbh="SD1", ajzybh="", fssj="", fymc="")],
        )
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


# ============================================================
# DocumentDeliveryRecord 测试
# ============================================================


class TestDocumentDeliveryRecord:
    def test_to_dict_with_time(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初123号",
            send_time=datetime(2025, 12, 10, 16, 25, 37),
            element_index=0,
            document_name="判决书",
            court_name="佛山法院",
        )
        d = record.to_dict()
        assert d["case_number"] == "（2025）粤0604民初123号"
        assert "2025-12-10" in d["send_time"]
        assert d["document_name"] == "判决书"

    def test_to_dict_no_time(self) -> None:
        record = DocumentDeliveryRecord(case_number="test", send_time=None, element_index=0)
        d = record.to_dict()
        assert d["send_time"] is None

    def test_from_dict_with_string_time(self) -> None:
        data = {
            "case_number": "test",
            "send_time": "2025-12-10T16:25:37",
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time is not None
        assert record.send_time.year == 2025

    def test_from_dict_with_datetime_time(self) -> None:
        data = {
            "case_number": "test",
            "send_time": datetime(2025, 1, 1),
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time == datetime(2025, 1, 1)

    def test_from_dict_no_time(self) -> None:
        data = {"case_number": "test", "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time is None


# ============================================================
# CaseMatcher 测试 (纯逻辑，mock 所有依赖)
# ============================================================


class TestCaseMatcher:
    """CaseMatcher 逻辑测试"""

    def _make_matcher(self, case_service=None, doc_parser=None, party_matcher=None):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        return CaseMatcher(
            case_service=case_service or MagicMock(),
            document_parser_service=doc_parser or MagicMock(),
            party_matching_service=party_matcher or MagicMock(),
        )

    def test_detect_case_type_civil(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_type_from_number("（2025）粤0605民初123号")
        assert result == "civil"

    def test_detect_case_type_criminal(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_type_from_number("（2025）粤0605刑初123号")
        assert result == "criminal"

    def test_detect_case_type_administrative(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_type_from_number("（2025）粤0605行初123号")
        assert result == "administrative"

    def test_detect_case_type_bankruptcy(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_type_from_number("（2025）粤0605破123号")
        assert result is None  # bankruptcy returns None for type

    def test_detect_case_type_empty(self) -> None:
        matcher = self._make_matcher()
        assert matcher._detect_case_type_from_number("") is None

    def test_is_bankruptcy_case_number_true(self) -> None:
        matcher = self._make_matcher()
        assert matcher._is_bankruptcy_case_number("（2025）粤0605破123号") is True

    def test_is_bankruptcy_case_number_false(self) -> None:
        matcher = self._make_matcher()
        assert matcher._is_bankruptcy_case_number("（2025）粤0605民初123号") is False

    def test_is_bankruptcy_case_number_empty(self) -> None:
        matcher = self._make_matcher()
        assert matcher._is_bankruptcy_case_number("") is False

    def test_detect_case_stage_enforcement(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_stage_from_number("（2025）粤0605执10286号")
        assert result == "enforcement"

    def test_detect_case_stage_first_trial(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_stage_from_number("（2025）粤0605民初123号")
        assert result == "first_trial"

    def test_detect_case_stage_second_trial(self) -> None:
        matcher = self._make_matcher()
        result = matcher._detect_case_stage_from_number("（2025）粤0605民终123号")
        assert result == "second_trial"

    def test_detect_case_stage_empty(self) -> None:
        matcher = self._make_matcher()
        assert matcher._detect_case_stage_from_number("") is None

    def test_select_latest_case_empty(self) -> None:
        matcher = self._make_matcher()
        assert matcher._select_latest_case([]) is None

    def test_select_latest_case_single(self) -> None:
        case = MagicMock()
        case.id = 1
        case.name = "test"
        case.current_stage = "first_trial"
        matcher = self._make_matcher()
        result = matcher._select_latest_case([case])
        assert result == case

    def test_select_latest_case_multiple(self) -> None:
        case1 = MagicMock()
        case1.id = 1
        case1.name = "old"
        case2 = MagicMock()
        case2.id = 2
        case2.name = "new"
        case2.current_stage = "first_trial"
        matcher = self._make_matcher()
        result = matcher._select_latest_case([case1, case2])
        assert result == case2

    def test_apply_type_filter_no_type(self) -> None:
        case1 = MagicMock()
        matcher = self._make_matcher()
        result = matcher._apply_type_filter([case1], None)
        assert result == [case1]

    def test_apply_type_filter_matching(self) -> None:
        case1 = MagicMock()
        case1.case_type = "civil"
        matcher = self._make_matcher()
        result = matcher._apply_type_filter([case1], "civil")
        assert result == [case1]

    def test_apply_type_filter_no_match_returns_original(self) -> None:
        case1 = MagicMock()
        case1.case_type = "criminal"
        matcher = self._make_matcher()
        result = matcher._apply_type_filter([case1], "civil")
        assert result == [case1]

    def test_apply_stage_filter_no_stage(self) -> None:
        case1 = MagicMock()
        matcher = self._make_matcher()
        result = matcher._apply_stage_filter([case1], None)
        assert result == [case1]

    def test_apply_stage_filter_matching(self) -> None:
        case1 = MagicMock()
        case1.current_stage = "enforcement"
        matcher = self._make_matcher()
        result = matcher._apply_stage_filter([case1], "enforcement")
        assert result == [case1]

    def test_extract_features_from_numbers(self) -> None:
        matcher = self._make_matcher()
        case_type, stage, is_bank = matcher._extract_features_from_numbers(
            ["（2025）粤0605民初123号"]
        )
        assert case_type == "civil"
        assert stage == "first_trial"
        assert is_bank is False

    def test_extract_features_bankruptcy(self) -> None:
        matcher = self._make_matcher()
        case_type, stage, is_bank = matcher._extract_features_from_numbers(
            ["（2025）粤0605破123号"]
        )
        assert is_bank is True

    def test_match_case_by_number_delegates(self) -> None:
        matcher = self._make_matcher()
        mock_case = MagicMock()
        matcher._case_service = MagicMock()
        with patch.object(matcher, '_match_by_case_number_exact', return_value=mock_case):
            result = matcher.match_by_case_number(["test"])
            assert result == mock_case

    def test_match_by_party_names_no_match(self) -> None:
        matcher = self._make_matcher()
        with patch.object(matcher, '_match_by_party_names_all', return_value=[]):
            result = matcher.match_by_party_names(["张三"])
            assert result is None

    def test_match_by_party_names_single(self) -> None:
        mock_case = MagicMock()
        matcher = self._make_matcher()
        with patch.object(matcher, '_match_by_party_names_all', return_value=[mock_case]):
            result = matcher.match_by_party_names(["张三"])
            assert result == mock_case

    def test_narrow_down_by_case_number_features_empty(self) -> None:
        matcher = self._make_matcher()
        assert matcher._narrow_down_by_case_number_features([], []) is None

    def test_narrow_down_by_case_number_features_no_features(self) -> None:
        case = MagicMock()
        matcher = self._make_matcher()
        # Empty case numbers -> no features extracted
        result = matcher._narrow_down_by_case_number_features([case], [])
        assert result is None

    def test_narrow_down_bankruptcy_filter(self) -> None:
        case1 = MagicMock()
        case1.name = "破产重整案件"
        case2 = MagicMock()
        case2.name = "普通民事案件"
        matcher = self._make_matcher()
        with patch.object(matcher, '_extract_features_from_numbers', return_value=(None, None, True)):
            result = matcher._narrow_down_by_case_number_features([case1, case2], ["（2025）破123号"])
            assert result == case1

    def test_extract_party_names_from_sms(self) -> None:
        matcher = self._make_matcher()
        sms = MagicMock()
        sms.party_names = ["张三", "李四"]
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_single_fallback_to_doc(self) -> None:
        matcher = self._make_matcher()
        sms = MagicMock()
        sms.party_names = ["张三"]
        matcher._document_parser_service = MagicMock()
        matcher._document_parser_service.get_all_document_paths.return_value = []
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]  # falls back to single party

    def test_extract_party_names_empty(self) -> None:
        matcher = self._make_matcher()
        sms = MagicMock()
        sms.party_names = []
        matcher._document_parser_service = MagicMock()
        matcher._document_parser_service.get_all_document_paths.return_value = []
        result = matcher._extract_party_names(sms)
        assert result == []


# ============================================================
# DocumentRenamer 测试
# ============================================================


class TestDocumentRenamer:
    """DocumentRenamer 测试"""

    @pytest.mark.django_db
    def test_generate_filename_basic(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer()
        filename = renamer.generate_filename("判决书", "张三与李四", date(2025, 6, 1))
        assert "判决书" in filename
        assert "20250601" in filename
        assert filename.endswith(".pdf")

    @pytest.mark.django_db
    def test_generate_filename_empty_title(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer()
        filename = renamer.generate_filename("", "案件名", date(2025, 1, 1))
        assert "司法文书" in filename

    @pytest.mark.django_db
    def test_generate_filename_empty_case_name(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer()
        filename = renamer.generate_filename("判决书", "", date(2025, 1, 1))
        assert "未知案件" in filename

    def test_sanitize_filename_part(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        assert renamer._sanitize_filename_part("test<>file") == "testfile"
        assert renamer._sanitize_filename_part("") == ""
        assert renamer._sanitize_filename_part("  file name ") == "file name"

    def test_normalize_title_candidate(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        result = renamer._normalize_title_candidate("佛山市禅城区人民法院受理通知书")
        assert "受理通知书" in result

    def test_match_title_from_text_known_title(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        result = renamer._match_title_from_text("本院受理张三与李四民间借贷纠纷一案，现将受理案件通知书送达给你。")
        assert result == "受理案件通知书"

    def test_match_title_from_text_empty(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        assert renamer._match_title_from_text("") is None

    def test_extract_title_from_filename(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        result = renamer._extract_title_from_filename("/path/to/受理通知书.pdf")
        assert result == "受理通知书"

    def test_extract_title_from_filename_unrecognized(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer.__new__(DocumentRenamer)
        renamer.title_extraction_limit = 50
        result = renamer._extract_title_from_filename("/path/to/abc123.pdf")
        assert result  # returns something, not empty
