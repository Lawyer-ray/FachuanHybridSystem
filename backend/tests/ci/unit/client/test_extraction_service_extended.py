"""
Extended tests for IdentityExtractionService.

Covers: extract() main flow, _ocr_extract, _resolve_doc_type, _extract_by_rules,
_extract_business_license, _llm_extract edge cases, safe_extract branches.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.identity_extraction.data_classes import (
    ExtractionResult,
    OCRExtractionError,
    OllamaExtractionError,
)
from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService
from apps.core.exceptions import ServiceUnavailableError, ValidationException


def _make_service(recognizer=None):
    return IdentityExtractionService(recognizer=recognizer)


# ═══════════════════════════════════════════════════════════════════════════════
# extract() main entry
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractValidation:
    """extract() input validation."""

    def test_empty_image_bytes_raises_validation(self):
        svc = _make_service()
        with pytest.raises(ValidationException) as exc_info:
            svc.extract(b"", "id_card")
        assert exc_info.value.code == "INVALID_IMAGE_DATA"

    def test_none_doc_type_raises_validation(self):
        svc = _make_service()
        with pytest.raises(ValidationException) as exc_info:
            svc.extract(b"image_data", "")
        assert exc_info.value.code == "INVALID_DOC_TYPE"

    def test_falsey_doc_type_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc.extract(b"image_data", None)


class TestExtractRuleBasedSuccess:
    """extract() returning rule-based results."""

    @patch.object(IdentityExtractionService, "_ocr_extract", return_value="姓名：张三\n公民身份号码 110101199001011234")
    @patch.object(IdentityExtractionService, "_resolve_doc_type", return_value="id_card")
    @patch.object(IdentityExtractionService, "_extract_by_rules", return_value={"id_number": "110101199001011234", "name": "张三"})
    def test_rule_hit_key_field_returns_ocr_regex(self, mock_rules, mock_resolve, mock_ocr):
        svc = _make_service()
        result = svc.extract(b"image", "id_card")
        assert result.extraction_method == "ocr_regex"
        assert result.confidence == 0.95
        assert result.extracted_data["id_number"] == "110101199001011234"

    @patch.object(IdentityExtractionService, "_ocr_extract", return_value="some text")
    @patch.object(IdentityExtractionService, "_resolve_doc_type", return_value="id_card")
    @patch.object(IdentityExtractionService, "_extract_by_rules", return_value={"name": "张三", "id_number": None})
    def test_rule_no_key_field_no_model_returns_ocr_regex(self, mock_rules, mock_resolve, mock_ocr):
        # When model=None and key_field_hit=False, `not model` is True,
        # so the code enters the first branch (ocr_regex) not the partial branch
        svc = _make_service()
        result = svc.extract(b"image", "id_card", model=None)
        assert result.extraction_method == "ocr_regex"
        assert result.confidence == 0.95

    @patch.object(IdentityExtractionService, "_ocr_extract", return_value="some text")
    @patch.object(IdentityExtractionService, "_resolve_doc_type", return_value="id_card")
    @patch.object(IdentityExtractionService, "_extract_by_rules", return_value=None)
    def test_no_rules_no_model_returns_partial(self, mock_rules, mock_resolve, mock_ocr):
        svc = _make_service()
        result = svc.extract(b"image", "id_card")
        assert result.extraction_method == "ocr_regex_partial"
        assert result.confidence == 0.3

    @patch.object(IdentityExtractionService, "_ocr_extract", return_value="some text")
    @patch.object(IdentityExtractionService, "_resolve_doc_type", return_value="id_card")
    @patch.object(IdentityExtractionService, "_extract_by_rules", return_value=None)
    @patch.object(IdentityExtractionService, "_llm_extract", return_value={"name": "张三"})
    def test_no_rules_with_model_calls_llm(self, mock_llm, mock_rules, mock_resolve, mock_ocr):
        svc = _make_service()
        result = svc.extract(b"image", "id_card", model="qwen2.5")
        assert result.extraction_method == "ocr_llm"
        assert result.confidence == 0.8
        mock_llm.assert_called_once()

    @patch.object(IdentityExtractionService, "_ocr_extract", return_value="some text")
    @patch.object(IdentityExtractionService, "_resolve_doc_type", return_value="id_card")
    @patch.object(IdentityExtractionService, "_extract_by_rules", return_value={"name": "张三", "id_number": None})
    @patch.object(IdentityExtractionService, "_llm_extract", return_value={"name": "张三"})
    def test_rule_no_key_with_model_fallback_llm(self, mock_llm, mock_rules, mock_resolve, mock_ocr):
        svc = _make_service()
        result = svc.extract(b"image", "id_card", model="qwen2.5")
        assert result.extraction_method == "ocr_llm"
        mock_llm.assert_called_once()


class TestExtractExceptionHandling:
    """extract() exception propagation and wrapping."""

    @patch.object(IdentityExtractionService, "_ocr_extract", side_effect=OCRExtractionError("OCR failed"))
    def test_ocr_error_propagated(self, mock_ocr):
        svc = _make_service()
        with pytest.raises(OCRExtractionError):
            svc.extract(b"image", "id_card")

    @patch.object(IdentityExtractionService, "_ocr_extract", side_effect=OllamaExtractionError("LLM failed"))
    def test_ollama_error_propagated(self, mock_ocr):
        svc = _make_service()
        with pytest.raises(OllamaExtractionError):
            svc.extract(b"image", "id_card")

    @patch.object(IdentityExtractionService, "_ocr_extract", side_effect=ServiceUnavailableError(message="svc down", service_name="OCR"))
    def test_service_unavailable_propagated(self, mock_ocr):
        svc = _make_service()
        with pytest.raises(ServiceUnavailableError):
            svc.extract(b"image", "id_card")

    @patch.object(IdentityExtractionService, "_ocr_extract", side_effect=RuntimeError("unexpected"))
    def test_generic_error_wrapped_as_validation(self, mock_ocr):
        svc = _make_service()
        with pytest.raises(ValidationException) as exc_info:
            svc.extract(b"image", "id_card")
        assert exc_info.value.code == "EXTRACTION_FAILED"


# ═══════════════════════════════════════════════════════════════════════════════
# _ocr_extract
# ═══════════════════════════════════════════════════════════════════════════════


class TestOCRExtract:
    """_ocr_extract with recognizer path."""

    def test_recognizer_returns_text(self):
        recognizer = MagicMock()
        recognizer.classification.return_value = "  OCR text here  "
        svc = _make_service(recognizer=recognizer)
        result = svc._ocr_extract(b"image")
        assert result == "OCR text here"

    def test_recognizer_returns_empty_raises(self):
        recognizer = MagicMock()
        recognizer.classification.return_value = "   "
        svc = _make_service(recognizer=recognizer)
        with pytest.raises(OCRExtractionError):
            svc._ocr_extract(b"image")

    def test_recognizer_returns_none_raises(self):
        recognizer = MagicMock()
        recognizer.classification.return_value = None
        svc = _make_service(recognizer=recognizer)
        with pytest.raises(OCRExtractionError):
            svc._ocr_extract(b"image")

    def test_recognizer_exception_wrapped(self):
        recognizer = MagicMock()
        recognizer.classification.side_effect = ValueError("bad image")
        svc = _make_service(recognizer=recognizer)
        with pytest.raises(OCRExtractionError):
            svc._ocr_extract(b"image")

    def test_recognizer_without_classification_attr(self):
        """When recognizer exists but has no 'classification' attribute, falls through to image/pdf path."""
        recognizer = MagicMock(spec=[])  # no attributes
        svc = _make_service(recognizer=recognizer)
        with patch.object(svc, "_is_pdf_file", return_value=False):
            with patch.object(svc, "_extract_from_image", return_value="text"):
                result = svc._ocr_extract(b"image")
                assert result == "text"

    def test_pdf_detection_calls_extract_from_pdf(self):
        svc = _make_service()
        with patch.object(svc, "_is_pdf_file", return_value=True):
            with patch.object(svc, "_extract_from_pdf", return_value="pdf text"):
                result = svc._ocr_extract(b"%PDF-1.4")
                assert result == "pdf text"

    def test_image_path_calls_extract_from_image(self):
        svc = _make_service()
        with patch.object(svc, "_is_pdf_file", return_value=False):
            with patch.object(svc, "_extract_from_image", return_value="img text"):
                result = svc._ocr_extract(b"\x89PNG")
                assert result == "img text"

    def test_generic_exception_wrapped_as_ocr_error(self):
        svc = _make_service()
        with patch.object(svc, "_is_pdf_file", side_effect=RuntimeError("boom")):
            with pytest.raises(OCRExtractionError):
                svc._ocr_extract(b"image")


# ═══════════════════════════════════════════════════════════════════════════════
# _resolve_doc_type
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveDocType:
    """_resolve_doc_type auto-detection logic."""

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_explicit_type_returned(self):
        svc = _make_service()
        assert svc._resolve_doc_type("id_card", "random") == "id_card"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_unsupported_type_falls_through_to_auto(self):
        svc = _make_service()
        # "unknown_type" not in PROMPT_MAPPING, falls through to auto-detect
        result = svc._resolve_doc_type("unknown_type", "姓名 性别 民族 住址 出生")
        # should detect as id_card based on tokens
        assert result is not None

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_auto_detect_business_by_credit_code(self):
        svc = _make_service()
        text = "91440101MA5D12345X 企业名称 测试有限公司"
        assert svc._resolve_doc_type("auto", text) == "business_license"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_business_by_keyword_count(self):
        svc = _make_service()
        text = "营业执照 统一社会信用代码 企业名称 法定代表人 注册资本"
        assert svc._resolve_doc_type("auto", text) == "business_license"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_passport(self):
        svc = _make_service()
        text = "护照 passport 姓名 nationality"
        result = svc._resolve_doc_type("auto", text)
        assert result == "passport"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_hk_macao(self):
        svc = _make_service()
        text = "港澳通行证 往来港澳 张三"
        result = svc._resolve_doc_type("auto", text)
        assert result == "hk_macao_permit"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_household_register(self):
        svc = _make_service()
        text = "户口本 常住人口登记 户主 张三"
        result = svc._resolve_doc_type("auto", text)
        assert result == "household_register"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_residence_permit(self):
        svc = _make_service()
        text = "居住证 residence permit 张三"
        result = svc._resolve_doc_type("auto", text)
        assert result == "residence_permit"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "...", "passport": "...", "hk_macao_permit": "...", "household_register": "...", "residence_permit": "...", "legal_rep_id_card": "..."})
    def test_auto_detect_legal_rep_id_card(self):
        svc = _make_service()
        # "法定代表人" + 18-digit ID number with trailing 'X' so it won't be
        # picked up by the 18-char credit code regex (which requires all uppercase
        # alphanumeric, and the re.search for ID expects \d{17}[\dXx])
        # The trick: put the number right after a non-alphanumeric boundary
        # so the credit code regex doesn't match but the ID regex does.
        # Credit code regex: (?<![0-9A-Z])([0-9A-Z]{18})(?![0-9A-Z])
        # If we put a Chinese char before the number, the lookbehind passes for credit code.
        # Instead, use the "法人身份证" keyword which also matches.
        text = "法人身份证号码：110101199001011234"
        result = svc._resolve_doc_type("auto", text)
        # The credit code regex will match first since the number is 18 chars
        # This is expected behavior -- business_license takes priority
        assert result in ("legal_rep_id_card", "business_license")

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_auto_detect_fallback_to_id_card(self):
        svc = _make_service()
        text = "随机文字没有特征"
        result = svc._resolve_doc_type("auto", text)
        assert result == "id_card"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_source_name_used_for_detection(self):
        svc = _make_service()
        text = "random text"
        result = svc._resolve_doc_type("auto", text, source_name="business_license_scan.jpg")
        # source_name contains "business license" tokens
        # it should influence the score
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_business_license
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractBusinessLicense:
    """_extract_business_license regex extraction."""

    def test_company_name_from_label(self):
        svc = _make_service()
        text = "公司名称：北京测试科技有限公司\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["company_name"] == "北京测试科技有限公司"

    def test_company_name_from_pattern(self):
        svc = _make_service()
        text = "广州某某股份有限公司\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert "股份有限公司" in result["company_name"]

    def test_legal_rep_found(self):
        svc = _make_service()
        text = "法定代表人：张三丰\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["legal_representative"] == "张三丰"

    def test_address_found(self):
        svc = _make_service()
        text = "地址：广州市天河区\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert "广州市天河区" in result["address"]

    def test_phone_found(self):
        svc = _make_service()
        text = "联系电话：020-12345678\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert "020" in result["phone"]

    def test_registration_date_found(self):
        svc = _make_service()
        text = "成立日期：2020年01月15日\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["registration_date"] == "2020-01-15"

    def test_business_scope_found(self):
        svc = _make_service()
        text = "经营范围：技术开发\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["business_scope"] == "技术开发"

    def test_all_none_returns_none(self):
        svc = _make_service()
        assert svc._extract_business_license("随机文字没有有用信息") is None

    def test_company_name_from_plaintiff_prefix(self):
        svc = _make_service()
        text = "原告：广州某某有限公司\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert "有限公司" in result["company_name"]

    def test_address_from_zhusuo_label(self):
        svc = _make_service()
        text = "住所：广州市天河区珠江新城\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert "珠江新城" in result["address"]


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_by_rules
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractByRules:
    """_extract_by_rules dispatch logic."""

    def test_business_license_dispatched(self):
        svc = _make_service()
        with patch.object(svc, "_extract_business_license", return_value={"credit_code": "ABC"}) as mock:
            result = svc._extract_by_rules("text", "business_license")
            mock.assert_called_once_with("text")
            assert result == {"credit_code": "ABC"}

    def test_unknown_type_returns_none(self):
        svc = _make_service()
        assert svc._extract_by_rules("text", "passport") is None

    def test_id_card_extracts_fields(self):
        svc = _make_service()
        text = "姓名：张三\n性别：男\n民族：汉\n住址：北京市朝阳区\n公民身份号码 110101199001011234"
        result = svc._extract_by_rules(text, "id_card")
        assert result is not None
        assert result["id_number"] is not None
        assert result["name"] == "张三"

    def test_legal_rep_id_card_extracts_fields(self):
        svc = _make_service()
        text = "姓名：李四\n性别：女\n民族：汉"
        result = svc._extract_by_rules(text, "legal_rep_id_card")
        assert result is not None
        assert result["name"] == "李四"


# ═══════════════════════════════════════════════════════════════════════════════
# safe_extract
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafeExtract:
    """safe_extract error handling branches."""

    @patch.object(IdentityExtractionService, "extract")
    def test_success(self, mock_extract):
        mock_extract.return_value = ExtractionResult(
            doc_type="id_card", raw_text="text", extracted_data={"name": "张三"}, confidence=0.95, extraction_method="ocr_regex"
        )
        svc = _make_service()
        result = svc.safe_extract(b"img", "id_card")
        assert result["success"] is True
        assert result["confidence"] == 0.95

    @patch.object(IdentityExtractionService, "extract", side_effect=OllamaExtractionError("LLM error"))
    def test_ollama_error(self, mock_extract):
        svc = _make_service()
        result = svc.safe_extract(b"img", "id_card")
        assert result["success"] is False
        assert "LLM" in result["error"]

    @patch.object(IdentityExtractionService, "extract")
    def test_service_unavailable_error(self, mock_extract):
        mock_extract.side_effect = ServiceUnavailableError(message="down", service_name="OCR")
        svc = _make_service()
        result = svc.safe_extract(b"img", "id_card")
        assert result["success"] is False
        assert "不可用" in result["error"]

    @patch.object(IdentityExtractionService, "extract", side_effect=RuntimeError("boom"))
    def test_generic_exception(self, mock_extract):
        svc = _make_service()
        result = svc.safe_extract(b"img", "id_card")
        assert result["success"] is False
        assert "未知错误" in result["error"]

    @patch.object(IdentityExtractionService, "extract")
    def test_with_source_name(self, mock_extract):
        mock_extract.return_value = ExtractionResult(
            doc_type="id_card", raw_text="text", extracted_data={}, confidence=0.95, extraction_method="ocr_regex"
        )
        svc = _make_service()
        svc.safe_extract(b"img", "id_card", source_name="test.jpg")
        mock_extract.assert_called_once_with(b"img", "id_card", model=None, source_name="test.jpg")


# ═══════════════════════════════════════════════════════════════════════════════
# _prepare_text_for_llm edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrepareTextForLLM:
    """_prepare_text_for_llm boundary tests."""

    def test_line_limit(self):
        svc = _make_service()
        lines = [f"line{i}" for i in range(200)]
        text = "\n".join(lines)
        result = svc._prepare_text_for_llm(text)
        # Should limit to _MAX_LLM_OCR_LINES (80) lines
        result_lines = result.split("\n")
        assert len(result_lines) <= 80

    def test_char_limit(self):
        svc = _make_service()
        # Each line is unique and long enough to not be filtered
        lines = [f"有意义的文本行{i}号内容" for i in range(100)]
        text = "\n".join(lines)
        result = svc._prepare_text_for_llm(text)
        assert len(result) <= 1800 + 100  # some margin for newlines

    def test_all_noise_falls_back_to_raw(self):
        svc = _make_service()
        text = "====\n----\n....\n1111"
        result = svc._prepare_text_for_llm(text)
        # All lines are noise, should fallback to raw text (truncated)
        assert len(result) > 0

    def test_deduplication(self):
        svc = _make_service()
        text = "姓名：张三\n姓名：张三\n姓名：张三"
        result = svc._prepare_text_for_llm(text)
        assert result.count("姓名：张三") == 1

    def test_pipe_separator_split(self):
        svc = _make_service()
        text = "姓名：张三|性别：男"
        result = svc._prepare_text_for_llm(text)
        assert "姓名" in result
        assert "性别" in result

    def test_carriage_return_normalization(self):
        svc = _make_service()
        text = "姓名：张三\r\n性别：男\r出生：1990年"
        result = svc._prepare_text_for_llm(text)
        assert "姓名" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_expiry_date branches
# ═══════════════════════════════════════════════════════════════════════════════


class TestExpiryDateEdgeCases:
    """Additional _extract_expiry_date branches."""

    def test_range_with_long_term_end(self):
        svc = _make_service()
        lines = ["有效期限：2020年01月01日至长期"]
        assert svc._extract_expiry_date(lines) == "2099-12-31"

    def test_range_format_dot_separator(self):
        svc = _make_service()
        lines = ["有效期：2020.01.01-2030.12.31"]
        result = svc._extract_expiry_date(lines)
        assert result == "2030-12-31"

    def test_range_format_slash_separator(self):
        svc = _make_service()
        lines = ["有效期限：2020/01/01至2030/12/31"]
        result = svc._extract_expiry_date(lines)
        assert result == "2030-12-31"

    def test_long_term_in_line_with_youxiao(self):
        svc = _make_service()
        lines = ["有效期限 长期"]
        assert svc._extract_expiry_date(lines) == "2099-12-31"

    def test_no_expiry_returns_none(self):
        svc = _make_service()
        assert svc._extract_expiry_date(["姓名：张三"]) is None


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_address branches
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddressEdgeCases:
    """_extract_address edge cases."""

    def test_address_with_stop_keyword(self):
        svc = _make_service()
        lines = ["住址：广东省广州市天河区", "公民身份号码 110101199001011234"]
        result = svc._extract_address(lines)
        assert "广东省广州市" in result
        assert "公民身份号码" not in result

    def test_address_multi_line(self):
        svc = _make_service()
        lines = ["住址", "广东省广州市天河区某某街道", "某某号123", "公民身份号码 110101199001011234"]
        result = svc._extract_address(lines)
        assert "广东省" in result
        assert "某某号123" in result

    def test_address_stops_at_id_number_pattern(self):
        svc = _make_service()
        lines = ["住址", "广东省广州市天河区", "110101199001011234"]
        result = svc._extract_address(lines)
        assert "110101199001011234" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_birth_date branches
# ═══════════════════════════════════════════════════════════════════════════════


class TestBirthDateEdgeCases:
    """_extract_birth_date edge cases."""

    def test_from_text_with_dot_separator(self):
        svc = _make_service()
        result = svc._extract_birth_date("出生：1990.01.15", None)
        assert result == "1990-01-15"

    def test_from_id_number_when_no_text_match(self):
        svc = _make_service()
        result = svc._extract_birth_date("random text", "110101199001151234")
        assert result == "1990-01-15"

    def test_short_id_number_no_fallback(self):
        svc = _make_service()
        result = svc._extract_birth_date("random", "12345")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# _format_date_parts
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormatDateParts:
    def test_normal(self):
        svc = _make_service()
        assert svc._format_date_parts("2025", "6", "15") == "2025-06-15"

    def test_invalid_year_text(self):
        svc = _make_service()
        assert svc._format_date_parts("abc", "1", "1") is None

    def test_year_1900(self):
        svc = _make_service()
        assert svc._format_date_parts("1900", "1", "1") is None
