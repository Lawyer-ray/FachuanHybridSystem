"""Final coverage tests for automation module — targeting uncovered service lines."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentProcessResult,
    DocumentQueryResult,
    DocumentRecord,
)
from apps.automation.services.ocr.paddleocr_api_service import (
    PaddleOCRApiEngine,
    PaddleOCRApiResult,
    _FILE_TYPE_IMAGE,
    _FILE_TYPE_PDF,
    _LAYOUT_ENDPOINT_MODELS,
    _MODEL_URL_KEY_MAP,
    _OCR_ENDPOINT_MODELS,
)


# ============================================================================
# DocumentRecord tests
# ============================================================================


class TestDocumentRecord:
    def test_parse_fssj_valid(self):
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="2025-12-10 16:25:37", fymc="f")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 10

    def test_parse_fssj_empty(self):
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="", fymc="f")
        assert rec.parse_fssj() is None

    def test_parse_fssj_iso_format(self):
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="2025-06-01T10:00:00", fymc="f")
        dt = rec.parse_fssj()
        assert dt is not None
        assert dt.hour == 10

    def test_parse_fssj_invalid(self):
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="not-a-date", fymc="f")
        assert rec.parse_fssj() is None

    def test_from_api_response(self):
        data = {
            "ah": "ah1", "sdbh": "sdbh1", "ajzybh": "aj1",
            "fssj": "2025-01-01 00:00:00", "fymc": "fy1",
            "ahdm": "dm1", "fybh": "fybh1", "ssdrxm": "name",
        }
        rec = DocumentRecord.from_api_response(data)
        assert rec.ah == "ah1"
        assert rec.ahdm == "dm1"
        assert rec.ssdrxm == "name"

    def test_to_dict_roundtrip(self):
        rec = DocumentRecord(ah="a", sdbh="b", ajzybh="c", fssj="d", fymc="e")
        d = rec.to_dict()
        assert d["ah"] == "a"
        assert d["sdbh"] == "b"
        assert "fssj" in d


class TestDocumentDetail:
    def test_from_api_response(self):
        data = {"c_sdbh": "s1", "c_wsmc": "w1", "c_wjgs": "pdf", "wjlj": "http://x"}
        dd = DocumentDetail.from_api_response(data)
        assert dd.c_sdbh == "s1"
        assert dd.wjlj == "http://x"

    def test_to_dict(self):
        dd = DocumentDetail(c_sdbh="s1", c_wsmc="w1", c_wjgs="pdf", wjlj="url")
        d = dd.to_dict()
        assert d["c_sdbh"] == "s1"


class TestDocumentListResponse:
    def test_from_api_response(self):
        data = {
            "code": 200,
            "data": {
                "total": 2,
                "data": [
                    {"ah": "a1", "sdbh": "s1", "ajzybh": "aj1", "fssj": "", "fymc": "f1"},
                    {"ah": "a2", "sdbh": "s2", "ajzybh": "aj2", "fssj": "", "fymc": "f2"},
                ],
            },
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2

    def test_to_dict(self):
        resp = DocumentListResponse(
            total=1,
            documents=[DocumentRecord(ah="a", sdbh="s", ajzybh="aj", fssj="", fymc="f")],
        )
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


class TestDocumentDeliveryRecord:
    def test_to_dict_with_send_time(self):
        dt = datetime(2025, 1, 15, 10, 30)
        rec = DocumentDeliveryRecord(
            case_number="cn", send_time=dt, element_index=1,
            document_name="doc", court_name="court", delivery_event_id="eid",
        )
        d = rec.to_dict()
        assert d["case_number"] == "cn"
        assert "2025-01-15" in d["send_time"]

    def test_to_dict_no_send_time(self):
        rec = DocumentDeliveryRecord(case_number="cn", send_time=None, element_index=0)
        d = rec.to_dict()
        assert d["send_time"] is None

    def test_from_dict_with_str_send_time(self):
        data = {
            "case_number": "cn", "send_time": "2025-01-15T10:30:00",
            "element_index": 1, "document_name": "doc",
        }
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.send_time is not None
        assert rec.send_time.year == 2025

    def test_from_dict_with_none_send_time(self):
        data = {"case_number": "cn", "send_time": None, "element_index": 0}
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.send_time is None

    def test_from_dict_with_datetime_send_time(self):
        dt = datetime(2025, 3, 1)
        data = {"case_number": "cn", "send_time": dt, "element_index": 2}
        rec = DocumentDeliveryRecord.from_dict(data)
        assert rec.send_time == dt


# ============================================================================
# PaddleOCRApiEngine tests
# ============================================================================


class TestPaddleOCRLooksLikeJsonNoise:
    def setup_method(self):
        self.engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)

    def test_short_string_not_noise(self):
        assert self.engine._looks_like_json_noise("hello") is False

    def test_json_object_noise(self):
        assert self.engine._looks_like_json_noise('{"key": "value", "a": 1}') is True

    def test_json_array_noise(self):
        assert self.engine._looks_like_json_noise('[{"a": 1}, {"b": 2}]') is True

    def test_json_key_value_pattern(self):
        text = "some text with " + '"field_name": "value"' + " more text here and there"
        assert self.engine._looks_like_json_noise(text) is True

    def test_high_json_char_ratio(self):
        text = "a" * 20 + "{}[]\":," * 5
        assert self.engine._looks_like_json_noise(text) is True

    def test_normal_text_not_noise(self):
        text = "这是一段正常的法律文书文本，没有任何JSON结构特征"
        assert self.engine._looks_like_json_noise(text) is False


class TestPaddleOCRCollectTextFragments:
    def setup_method(self):
        self.engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)

    def test_none_value(self):
        assert self.engine._collect_text_fragments(None) == []

    def test_string_value(self):
        assert self.engine._collect_text_fragments("hello world") == ["hello world"]

    def test_empty_string(self):
        assert self.engine._collect_text_fragments("") == []

    def test_list_value(self):
        result = self.engine._collect_text_fragments(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_dict_with_priority_keys(self):
        d = {"text": "hello", "other": "world"}
        result = self.engine._collect_text_fragments(d)
        assert "hello" in result

    def test_dict_with_markdown_key(self):
        d = {"markdown": "some markdown content"}
        result = self.engine._collect_text_fragments(d)
        assert "some markdown content" in result

    def test_nested_structure(self):
        d = {"outer": {"inner": {"text": "nested"}}}
        result = self.engine._collect_text_fragments(d)
        assert "nested" in result

    def test_integer_value(self):
        result = self.engine._collect_text_fragments(42)
        assert "42" in result


class TestPaddleOCRCollectRecTexts:
    def setup_method(self):
        self.engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)

    def test_none_value(self):
        assert self.engine._collect_rec_texts(None) == []

    def test_json_string(self):
        result = self.engine._collect_rec_texts('{"rec_texts": ["text1", "text2"]}')
        assert "text1" in result
        assert "text2" in result

    def test_invalid_json_string(self):
        result = self.engine._collect_rec_texts("{invalid json")
        assert result == []

    def test_list_of_dicts(self):
        result = self.engine._collect_rec_texts([{"rec_texts": ["a", "b"]}])
        assert "a" in result

    def test_nested_dict_with_rec_texts(self):
        d = {"result": {"ocrResults": {"rec_texts": ["line1", "line2"]}}}
        result = self.engine._collect_rec_texts(d)
        assert "line1" in result

    def test_empty_rec_texts(self):
        result = self.engine._collect_rec_texts({"rec_texts": []})
        assert result == []

    def test_deduplication(self):
        d = {"rec_texts": ["dup", "dup", "unique"]}
        result = self.engine._collect_rec_texts(d)
        assert result.count("dup") == 1


class TestPaddleOCRParseResponse:
    def setup_method(self):
        self.engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)

    def test_parse_ocr_response_with_rec_texts(self):
        data = {
            "result": {
                "ocrResults": [
                    {"prunedResult": {"rec_texts": ["line1", "line2"]}},
                ],
            },
        }
        result = self.engine._parse_response(data, "pp_ocrv5")
        assert isinstance(result, PaddleOCRApiResult)
        assert "line1" in result.text
        assert result.model == "pp_ocrv5"

    def test_parse_layout_response(self):
        data = {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "# Title\n\nBody text"}},
                ],
            },
        }
        result = self.engine._parse_response(data, "paddleocr_vl")
        assert isinstance(result, PaddleOCRApiResult)
        assert result.model == "paddleocr_vl"

    def test_parse_unsupported_model(self):
        data = {"result": {}}
        with pytest.raises(RuntimeError, match="不支持的 PaddleOCR 模型"):
            self.engine._parse_response(data, "unknown_model")


class TestPaddleOCRModelProperty:
    @patch.object(PaddleOCRApiEngine, "_config_service", create=True)
    def test_model_from_init(self, mock_config):
        engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)
        engine._model = "paddleocr_vl"
        engine._config_service = mock_config
        assert engine.model == "paddleocr_vl"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_model_from_config(self, MockConfig):
        mock_config = Mock()
        mock_config.get_value.return_value = "pp_structure_v3"
        MockConfig.return_value = mock_config
        engine = PaddleOCRApiEngine(model=None)
        assert engine.model == "pp_structure_v3"


class TestPaddleOCRModelUrlKeyMap:
    def test_all_models_have_url_keys(self):
        all_models = _OCR_ENDPOINT_MODELS | _LAYOUT_ENDPOINT_MODELS
        for model in all_models:
            assert model in _MODEL_URL_KEY_MAP

    def test_file_type_constants(self):
        assert _FILE_TYPE_PDF == 0
        assert _FILE_TYPE_IMAGE == 1


# ============================================================================
# DocumentDeliveryScheduleService tests (partial, mock DB)
# ============================================================================


class TestValidateScheduleConfig:
    def _get_service(self):
        from apps.automation.services.document_delivery.document_delivery_schedule_service import (
            DocumentDeliveryScheduleService,
        )
        return DocumentDeliveryScheduleService.__new__(DocumentDeliveryScheduleService)

    def test_valid_config(self):
        svc = self._get_service()
        svc._validate_schedule_config(1, 24, 24)  # should not raise

    def test_zero_runs_per_day(self):
        from apps.core.exceptions import ValidationException
        svc = self._get_service()
        with pytest.raises(ValidationException):
            svc._validate_schedule_config(0, 24, 24)

    def test_negative_hour_interval(self):
        from apps.core.exceptions import ValidationException
        svc = self._get_service()
        with pytest.raises(ValidationException):
            svc._validate_schedule_config(1, -1, 24)

    def test_zero_cutoff_hours(self):
        from apps.core.exceptions import ValidationException
        svc = self._get_service()
        with pytest.raises(ValidationException):
            svc._validate_schedule_config(1, 24, 0)

    def test_frequency_too_high(self):
        from apps.core.exceptions import ValidationException
        svc = self._get_service()
        with pytest.raises(ValidationException):
            svc._validate_schedule_config(10, 3, 24)  # 10*3=30>24

    def test_hour_interval_over_24(self):
        from apps.core.exceptions import ValidationException
        svc = self._get_service()
        with pytest.raises(ValidationException):
            svc._validate_schedule_config(1, 25, 24)


class TestCalculateNextRunTime:
    def _get_service(self):
        from apps.automation.services.document_delivery.document_delivery_schedule_service import (
            DocumentDeliveryScheduleService,
        )
        svc = DocumentDeliveryScheduleService.__new__(DocumentDeliveryScheduleService)
        return svc

    @patch("apps.automation.services.document_delivery.document_delivery_schedule_service.timezone")
    def test_single_run(self, mock_tz):
        mock_tz.now.return_value = datetime(2025, 1, 1, 12, 0)
        svc = self._get_service()
        result = svc._calculate_next_run_time(1, 24)
        assert result.hour == 12

    @patch("apps.automation.services.document_delivery.document_delivery_schedule_service.timezone")
    def test_multiple_runs(self, mock_tz):
        mock_tz.now.return_value = datetime(2025, 1, 1, 8, 0)
        svc = self._get_service()
        result = svc._calculate_next_run_time(3, 8)
        assert result.hour == 16


class TestGetExecutionLockKey:
    def test_lock_key_format(self):
        from apps.automation.services.document_delivery.document_delivery_schedule_service import (
            DocumentDeliveryScheduleService,
        )
        svc = DocumentDeliveryScheduleService.__new__(DocumentDeliveryScheduleService)
        key = svc._get_execution_lock_key(42)
        assert "42" in key
        assert "lock" in key


# ============================================================================
# InsuranceClient parse tests
# ============================================================================


class TestParseInsuranceCompanies:
    def _make_client(self):
        from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
        client = CourtInsuranceClient.__new__(CourtInsuranceClient)
        return client

    def test_parse_dict_with_data_key(self):
        client = self._make_client()
        data = {
            "data": [
                {"cId": "1", "cCode": "C1", "cName": "Company1"},
                {"cId": "2", "cCode": "C2", "cName": "Company2"},
            ]
        }
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 2
        assert companies[0].c_name == "Company1"

    def test_parse_list_directly(self):
        client = self._make_client()
        data = [
            {"cId": "1", "cCode": "C1", "cName": "Company1"},
        ]
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1

    def test_parse_unknown_format(self):
        client = self._make_client()
        companies = client._parse_insurance_companies("not a dict or list")
        assert companies == []

    def test_parse_incomplete_items(self):
        client = self._make_client()
        data = [
            {"cId": "1", "cCode": "C1"},  # missing cName
            {"cId": "2", "cCode": "C2", "cName": "Full"},
        ]
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1
        assert companies[0].c_name == "Full"

    def test_parse_non_dict_items(self):
        client = self._make_client()
        data = [123, "string", {"cId": "1", "cCode": "C1", "cName": "OK"}]
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1


# ============================================================================
# SMS Document Mixin tests
# ============================================================================


class TestSMSDocumentMixinExtractFromSingleDocument:
    def _make_mixin(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mock_cne = MagicMock()
        mock_matcher = MagicMock()
        # Create subclass that overrides the properties
        class TestMixin(SMSDocumentMixin):
            @property
            def case_number_extractor(self):
                return mock_cne
            @property
            def matcher(self):
                return mock_matcher
        mixin = TestMixin.__new__(TestMixin)
        return mixin, mock_cne, mock_matcher

    def test_extract_both_case_numbers_and_parties(self):
        mixin, mock_cne, mock_matcher = self._make_mixin()
        mock_cne.extract_from_document.return_value = ["(2025)粤01号"]
        mock_matcher.extract_parties_from_document.return_value = ["张三"]
        case_numbers: list[str] = []
        party_names: list[str] = []
        updated = mixin._extract_from_single_document("/fake/path.pdf", case_numbers, party_names)
        assert updated is True
        assert case_numbers == ["(2025)粤01号"]
        assert party_names == ["张三"]

    def test_extract_already_has_case_numbers(self):
        mixin, mock_cne, mock_matcher = self._make_mixin()
        case_numbers = ["existing"]
        party_names: list[str] = []
        mock_matcher.extract_parties_from_document.return_value = ["李四"]
        updated = mixin._extract_from_single_document("/f.pdf", case_numbers, party_names)
        assert updated is True
        mock_cne.extract_from_document.assert_not_called()

    def test_extract_exception_returns_false(self):
        mixin, mock_cne, mock_matcher = self._make_mixin()
        mock_cne.extract_from_document.side_effect = Exception("boom")
        result = mixin._extract_from_single_document("/f.pdf", [], [])
        assert result is False

    def test_extract_no_results(self):
        mixin, mock_cne, mock_matcher = self._make_mixin()
        mock_cne.extract_from_document.return_value = []
        mock_matcher.extract_parties_from_document.return_value = []
        result = mixin._extract_from_single_document("/f.pdf", [], [])
        assert result is False


class TestSMSDocumentMixinExtractAndUpdate:
    def test_skip_no_scraper_task(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.scraper_task = None
        sms.id = 1
        mixin._extract_and_update_sms_from_documents(sms)  # should not raise

    def test_skip_no_document_paths(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        mixin._get_document_paths_for_extraction = MagicMock(return_value=[])
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.id = 1
        mixin._extract_and_update_sms_from_documents(sms)


class TestSMSDocumentMixinSaveRenamedPaths:
    def test_save_renamed_paths(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.scraper_task = MagicMock()
        sms.scraper_task.result = {}
        mixin._save_renamed_paths(sms, ["/a.pdf", "/b.pdf"])
        assert sms.scraper_task.result["renamed_files"] == ["/a.pdf", "/b.pdf"]

    def test_save_empty_paths(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        mixin._save_renamed_paths(sms, [])
        sms.scraper_task.save.assert_not_called()


class TestSMSDocumentMixinArchiveToCaseFolder:
    def test_skip_no_case_id(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.case_id = None
        mixin._archive_to_case_folder(sms, ["/a.pdf"])

    def test_skip_empty_paths(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.case_id = 1
        mixin._archive_to_case_folder(sms, [])


class TestSMSDocumentMixinSyncPartyNames:
    def test_skip_no_renamed_paths(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.party_names = []
        mixin._sync_party_names_from_documents(sms, [])

    def test_skip_already_has_parties(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin
        mixin = SMSDocumentMixin.__new__(SMSDocumentMixin)
        sms = MagicMock()
        sms.party_names = ["existing"]
        mixin._sync_party_names_from_documents(sms, ["/a.pdf"])


# ============================================================================
# TianyanchaResponseAdapter tests
# ============================================================================


class TestTianyanchaPickStr:
    def test_pick_first_match(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        obj = {"name": "value1", "alt": "value2"}
        assert TianyanchaResponseAdapter.pick_str(obj, ("name", "alt")) == "value1"

    def test_pick_fallback(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        obj = {"alt": "val"}
        assert TianyanchaResponseAdapter.pick_str(obj, ("missing", "alt")) == "val"

    def test_pick_none_value(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        obj = {"key": None, "alt": "val"}
        assert TianyanchaResponseAdapter.pick_str(obj, ("key", "alt")) == "val"

    def test_pick_empty_string(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        obj = {"key": "  ", "alt": "val"}
        assert TianyanchaResponseAdapter.pick_str(obj, ("key", "alt")) == "val"

    def test_pick_no_match(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        obj = {"a": "b"}
        assert TianyanchaResponseAdapter.pick_str(obj, ("x", "y")) == ""


class TestTianyanchaExtractItems:
    def setup_method(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        self.adapter = TianyanchaResponseAdapter()

    def test_list_input(self):
        data = [{"id": 1}, {"id": 2}, "not a dict"]
        result = self.adapter.extract_items(data)
        assert len(result) == 2

    def test_dict_with_items_key(self):
        data = {"items": [{"id": 1}]}
        result = self.adapter.extract_items(data)
        assert len(result) == 1

    def test_dict_with_nested_data(self):
        data = {"data": {"rows": [{"id": 1}, {"id": 2}]}}
        result = self.adapter.extract_items(data)
        assert len(result) == 2

    def test_non_dict_non_list(self):
        result = self.adapter.extract_items("string")
        assert result == []

    def test_dict_with_list_key_data(self):
        data = {"data": [{"id": 1}]}
        result = self.adapter.extract_items(data)
        assert len(result) == 1


class TestTianyanchaExtractPrimaryDict:
    def setup_method(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        self.adapter = TianyanchaResponseAdapter()

    def test_dict_with_dict_value(self):
        data = {"data": {"name": "test"}}
        result = self.adapter.extract_primary_dict(data)
        assert result["name"] == "test"

    def test_dict_with_list_value(self):
        data = {"data": [{"name": "first"}, {"name": "second"}]}
        result = self.adapter.extract_primary_dict(data)
        assert result["name"] == "first"

    def test_list_input(self):
        data = [{"name": "a"}, {"name": "b"}]
        result = self.adapter.extract_primary_dict(data)
        assert result["name"] == "a"

    def test_non_dict_non_list(self):
        result = self.adapter.extract_primary_dict("string")
        assert result == {}

    def test_list_with_no_dicts(self):
        result = self.adapter.extract_primary_dict([1, 2, 3])
        assert result == {}


class TestTianyanchaMarkdownParsing:
    def setup_method(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        self.adapter = TianyanchaResponseAdapter()

    def test_parse_search_markdown(self):
        md = """# 企业搜索结果

## 1. 测试公司A

| **企业ID** | 12345 |
| **法定代表人** | 张三 |
| **经营状态** | 存续 |
| **成立时间** | 2020-01-01 |
| **注册资本** | 100万 |
| **联系电话** | 13800138000 |

## 2. 测试公司B

| **企业ID** | 67890 |
| **法定代表人** | 李四 |
"""
        result = self.adapter.parse_search_companies_markdown(md)
        assert len(result) == 2
        assert result[0]["company_name"] == "测试公司A"
        assert result[0]["company_id"] == "12345"
        assert result[0]["legal_person"] == "张三"
        assert result[1]["company_name"] == "测试公司B"

    def test_parse_search_markdown_no_results(self):
        result = self.adapter.parse_search_companies_markdown("just some text")
        assert result == []

    def test_parse_company_profile_markdown(self):
        md = """# 🏢 测试公司

| **企业ID** | 123 |
| **统一社会信用代码** | 9111... |
| **法定代表人** | 张三 |
| **经营状态** | 存续 |
| **成立日期** | 2020-01-01 |
| **注册资本** | 100万 |
| **注册地址** | 北京市 |
| **联系电话** | 010-1234 |

## 📄 经营范围

技术开发、技术咨询

**关于企业更多信息**
"""
        result = self.adapter.parse_company_profile_markdown(md)
        assert result["company_name"] == "测试公司"
        assert result["company_id"] == "123"
        assert result["unified_social_credit_code"] == "9111..."
        assert result["legal_person"] == "张三"

    def test_parse_company_profile_empty(self):
        result = self.adapter.parse_company_profile_markdown("")
        assert result == {}

    def test_parse_company_profile_from_dict(self):
        payload = {"result": "some markdown without enterprise info"}
        result = self.adapter.parse_company_profile_markdown(payload)
        assert result == {}

    def test_extract_markdown_from_dict_with_text_key(self):
        result = self.adapter._extract_markdown_result({"text": "hello"})
        assert result == "hello"

    def test_extract_markdown_from_dict_with_message_key(self):
        result = self.adapter._extract_markdown_result({"message": "msg"})
        assert result == "msg"

    def test_extract_markdown_non_str_non_dict(self):
        result = self.adapter._extract_markdown_result(42)
        assert result == ""


class TestTianyanchaNormalizeMethods:
    def setup_method(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        self.adapter = TianyanchaResponseAdapter()

    def test_normalize_company_summary(self):
        item = {
            "companyId": "123",
            "companyName": "TestCo",
            "legalPersonName": "Zhang",
            "regStatus": "Active",
            "estiblishTime": "2020-01-01",
            "regCapital": "100万",
            "phone": "123",
        }
        result = self.adapter.normalize_company_summary(item)
        assert result["company_id"] == "123"
        assert result["company_name"] == "TestCo"

    def test_normalize_company_profile(self):
        item = {
            "id": "456",
            "name": "TestCo2",
            "creditCode": "USCC123",
            "legal_person": "Li",
            "status": "正常",
            "estiblishTime": "2019-01-01",
            "regCapital": "200万",
            "regLocation": "地址",
            "businessScope": "经营范围",
            "phone": "456",
        }
        result = self.adapter.normalize_company_profile(item)
        assert result["company_id"] == "456"
        assert result["unified_social_credit_code"] == "USCC123"

    def test_normalize_risk_item(self):
        item = {"riskType": "court", "title": "诉讼", "level": "high", "amount": "10000", "date": "2025-01-01", "source": "法院"}
        result = self.adapter.normalize_risk_item(item, fallback_risk_type="unknown")
        assert result["risk_type"] == "court"
        assert result["title"] == "诉讼"

    def test_normalize_risk_item_fallback(self):
        item = {"title": "test"}
        result = self.adapter.normalize_risk_item(item, fallback_risk_type="default_type")
        assert result["risk_type"] == "default_type"

    def test_normalize_shareholder_item(self):
        item = {"name": "股东A", "subConAm": "100万", "holdRatio": "50%", "conDate": "2020-01"}
        result = self.adapter.normalize_shareholder_item(item)
        assert result["name"] == "股东A"
        assert result["amount"] == "100万"

    def test_normalize_personnel_item(self):
        item = {"name": "王五", "position": "经理", "education": "硕士"}
        result = self.adapter.normalize_personnel_item(item)
        assert result["name"] == "王五"
        assert result["position"] == "经理"

    def test_normalize_person_profile(self):
        item = {"name": "赵六", "position": "董事", "intro": "简介", "resume": "简历"}
        result = self.adapter.normalize_person_profile(item)
        assert result["name"] == "赵六"
        assert result["intro"] == "简介"

    def test_normalize_bidding_item(self):
        item = {
            "title": "招标公告", "projectName": "项目A", "role": "中标",
            "amount": "100万", "date": "2025-01-01", "region": "北京", "url": "http://x",
        }
        result = self.adapter.normalize_bidding_item(item)
        assert result["title"] == "招标公告"
        assert result["project_name"] == "项目A"
        assert result["link"] == "http://x"


class TestTianyanchaCleanMarkdownValue:
    def test_clean_bold(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        assert TianyanchaResponseAdapter._clean_markdown_value("**bold**") == "bold"

    def test_clean_backticks(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        assert TianyanchaResponseAdapter._clean_markdown_value("`code`") == "code"

    def test_clean_none(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        assert TianyanchaResponseAdapter._clean_markdown_value(None) == ""

    def test_clean_whitespace(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        result = TianyanchaResponseAdapter._clean_markdown_value("  hello  world  ")
        assert result == "hello world"

    def test_clean_tabs(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import (
            TianyanchaResponseAdapter,
        )
        result = TianyanchaResponseAdapter._clean_markdown_value("a\tb")
        assert result == "a b"
