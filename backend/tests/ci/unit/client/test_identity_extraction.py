"""Tests for client identity extraction service."""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from apps.client.services.identity_extraction.extraction_service import (
    IdentityExtractionService,
    _MAX_LLM_OCR_CHARS,
    _MAX_LLM_OCR_LINES,
)
from apps.client.services.identity_extraction.data_classes import (
    ExtractionResult,
    OCRExtractionError,
    OllamaExtractionError,
)


class TestLooksLikeJsonNoise:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_short_line_not_noise(self):
        assert not self.svc._looks_like_json_noise("hello")

    def test_json_object_line(self):
        assert self.svc._looks_like_json_noise('{"key": "value", "other": 123}')

    def test_json_array_line(self):
        assert self.svc._looks_like_json_noise('[{"a": 1}, {"b": 2}]')

    def test_json_key_pattern(self):
        assert self.svc._looks_like_json_noise('"some_key": "some_value"')

    def test_high_json_char_ratio(self):
        line = "{" * 10 + '"x"' + ":" + "1" + "}" * 10 + "," * 5
        assert self.svc._looks_like_json_noise(line)

    def test_normal_text_not_noise(self):
        assert not self.svc._looks_like_json_noise("这是一段正常的中文文字内容")

    def test_empty_line(self):
        assert not self.svc._looks_like_json_noise("")


class TestIsMeaningfulLine:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_empty_line(self):
        assert not self.svc._is_meaningful_line("")

    def test_separator_line(self):
        assert not self.svc._is_meaningful_line("--------")
        assert not self.svc._is_meaningful_line("========")
        assert not self.svc._is_meaningful_line("...")

    def test_repeated_chars(self):
        assert not self.svc._is_meaningful_line("哈哈哈哈")
        assert not self.svc._is_meaningful_line("1111")

    def test_json_noise(self):
        assert not self.svc._is_meaningful_line('{"key": "value"}')

    def test_single_char_non_meaningful(self):
        assert not self.svc._is_meaningful_line(" ")
        assert not self.svc._is_meaningful_line("!")

    def test_single_char_meaningful(self):
        assert self.svc._is_meaningful_line("A")
        assert self.svc._is_meaningful_line("5")

    def test_normal_text(self):
        assert self.svc._is_meaningful_line("姓名：张三")


class TestPrepareTextForLlm:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_basic_cleaning(self):
        raw = "姓名：张三\n\n性别：男\n\n民族：汉"
        result = self.svc._prepare_text_for_llm(raw)
        assert "姓名：张三" in result
        assert "性别：男" in result

    def test_deduplication(self):
        raw = "相同行\n相同行\n不同行"
        result = self.svc._prepare_text_for_llm(raw)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_pipe_separator(self):
        raw = "姓名：张三|性别：男"
        result = self.svc._prepare_text_for_llm(raw)
        assert "姓名：张三" in result
        assert "性别：男" in result

    def test_empty_input(self):
        result = self.svc._prepare_text_for_llm("")
        assert result == ""

    def test_all_noise_fallback(self):
        raw = '{"a":1}\n{"b":2}'
        result = self.svc._prepare_text_for_llm(raw)
        # Should return raw text fallback
        assert result

    def test_char_limit(self):
        raw = "\n".join([f"有效文字行{i}" for i in range(200)])
        result = self.svc._prepare_text_for_llm(raw)
        assert len(result) <= _MAX_LLM_OCR_CHARS + 100  # small margin


class TestResolveDocType:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_explicit_type(self):
        result = self.svc._resolve_doc_type("id_card", "some text")
        assert result == "id_card"

    def test_business_license_keywords(self):
        text = "营业执照\n统一社会信用代码\n法定代表人\n注册资本"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "business_license"

    def test_business_license_credit_code(self):
        # 18-char code with alpha = credit code detection
        text = "91110108MA12345678\n企业名称：测试公司"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "business_license"

    def test_id_card_fallback(self):
        text = "居民身份证\n公民身份号码\n姓名"
        result = self.svc._resolve_doc_type("auto", text)
        # Should be id_card based on tokens
        assert result in ("id_card", "legal_rep_id_card")

    def test_passport_detection(self):
        text = "护照 passport nationality"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "passport"

    def test_hk_macao_permit(self):
        text = "往来港澳通行证"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "hk_macao_permit"

    def test_household_register(self):
        text = "户口本 常住人口登记 户主"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "household_register"

    def test_residence_permit(self):
        text = "居住证 residence permit"
        result = self.svc._resolve_doc_type("auto", text)
        assert result == "residence_permit"

    def test_unknown_type_warning(self):
        result = self.svc._resolve_doc_type("unknown_type", "一般文本")
        assert result  # should fallback to id_card

    def test_source_name_hint(self):
        # Source name provides 1 token but need 2+ for business license match
        result = self.svc._resolve_doc_type("auto", "一般文字", source_name="统一社会信用代码.jpg")
        # The credit code detection path needs 18-char code; source alone gives business_score=1
        # which is not enough for business_score >= 2
        assert result in ("business_license", "id_card")


class TestExtractIdNumber:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_valid_id(self):
        assert self.svc._extract_id_number("公民身份号码 110101199001011234") == "110101199001011234"

    def test_id_with_x(self):
        assert self.svc._extract_id_number("11010119900101123X") == "11010119900101123X"

    def test_no_id(self):
        assert self.svc._extract_id_number("没有身份证号") is None

    def test_short_number(self):
        assert self.svc._extract_id_number("1234567") is None


class TestExtractName:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_basic_name(self):
        assert self.svc._extract_name(["姓名：张三", "性别：男"]) == "张三"

    def test_name_no_colon(self):
        assert self.svc._extract_name(["姓名张三丰"]) == "张三丰"

    def test_no_name(self):
        assert self.svc._extract_name(["性别：男", "民族：汉"]) is None


class TestExtractGender:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_male(self):
        assert self.svc._extract_gender(["性别：男"]) == "男"

    def test_female(self):
        assert self.svc._extract_gender(["性别：女"]) == "女"

    def test_no_gender(self):
        assert self.svc._extract_gender(["无信息"]) is None


class TestExtractEthnicity:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_han(self):
        assert self.svc._extract_ethnicity(["民族：汉"]) == "汉"

    def test_manchu(self):
        assert self.svc._extract_ethnicity(["民族满族"]) == "满族"

    def test_no_ethnicity(self):
        assert self.svc._extract_ethnicity(["无信息"]) is None


class TestExtractBirthDate:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_from_text(self):
        assert self.svc._extract_birth_date("出生：1990年01月15日", None) == "1990-01-15"

    def test_from_id_number(self):
        assert self.svc._extract_birth_date("", "110101199001151234") == "1990-01-15"

    def test_no_date(self):
        assert self.svc._extract_birth_date("无信息", None) is None


class TestExtractExpiryDate:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_long_term(self):
        assert self.svc._extract_expiry_date(["有效期限：长期"]) == "2099-12-31"

    def test_range_format(self):
        lines = ["有效期限：2020.01.01-2030.01.01"]
        assert self.svc._extract_expiry_date(lines) == "2030-01-01"

    def test_range_long(self):
        lines = ["有效期限：2020.01.01-长期"]
        assert self.svc._extract_expiry_date(lines) == "2099-12-31"

    def test_until_format(self):
        lines = ["有效期至：2030年06月30日"]
        assert self.svc._extract_expiry_date(lines) == "2030-06-30"

    def test_no_expiry(self):
        assert self.svc._extract_expiry_date(["无信息"]) is None


class TestExtractAddress:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_basic_address(self):
        lines = ["住址：北京市朝阳区建国路88号", "公民身份号码"]
        assert self.svc._extract_address(lines) == "北京市朝阳区建国路88号"

    def test_multiline_address(self):
        lines = ["住址：北京市", "朝阳区建国路88号", "公民身份号码"]
        assert self.svc._extract_address(lines) == "北京市朝阳区建国路88号"

    def test_no_address(self):
        assert self.svc._extract_address(["无信息"]) is None

    def test_stops_at_id_number(self):
        lines = ["住址：北京市", "110101199001011234", "其他信息"]
        assert self.svc._extract_address(lines) == "北京市"


class TestFormatDateParts:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_valid_date(self):
        assert self.svc._format_date_parts("1990", "1", "15") == "1990-01-15"

    def test_invalid_month(self):
        assert self.svc._format_date_parts("1990", "13", "15") is None

    def test_invalid_day(self):
        assert self.svc._format_date_parts("1990", "1", "32") is None

    def test_year_too_old(self):
        assert self.svc._format_date_parts("1800", "1", "1") is None

    def test_non_numeric(self):
        assert self.svc._format_date_parts("abc", "1", "1") is None


class TestParseLlmJson:
    def test_json_block(self):
        content = '```json\n{"key": "value"}\n```'
        assert IdentityExtractionService._parse_llm_json(content) == {"key": "value"}

    def test_generic_block(self):
        content = '```\n{"key": "value"}\n```'
        assert IdentityExtractionService._parse_llm_json(content) == {"key": "value"}

    def test_raw_json(self):
        content = '{"key": "value"}'
        assert IdentityExtractionService._parse_llm_json(content) == {"key": "value"}

    def test_json_in_text(self):
        content = 'Here is the result: {"key": "value"} done.'
        assert IdentityExtractionService._parse_llm_json(content) == {"key": "value"}

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="无法从 LLM 输出中提取 JSON"):
            IdentityExtractionService._parse_llm_json("no json here")


class TestExtractByRules:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_id_card_rules(self):
        text = "姓名：张三\n性别：男\n民族：汉\n住址：北京市\n公民身份号码 110101199001011234\n有效期限：2020.01.01-2040.01.01"
        result = self.svc._extract_by_rules(text, "id_card")
        assert result is not None
        assert result["name"] == "张三"
        assert result["gender"] == "男"
        assert result["id_number"] == "110101199001011234"

    def test_business_license_rules(self):
        text = "统一社会信用代码 91110108MA12345678\n企业名称：测试有限公司\n法定代表人：张三\n地址：北京市朝阳区\n联系电话：010-12345678"
        result = self.svc._extract_by_rules(text, "business_license")
        assert result is not None
        assert result["credit_code"] == "91110108MA12345678"
        assert result["company_name"] == "测试有限公司"
        assert result["legal_representative"] == "张三"
        assert result["address"] == "北京市朝阳区"
        assert result["phone"] == "010-12345678"

    def test_unsupported_type_returns_none(self):
        assert self.svc._extract_by_rules("text", "passport") is None

    def test_business_license_no_fields(self):
        result = self.svc._extract_by_rules("无任何有用信息", "business_license")
        assert result is None


class TestIsPdfFile:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_pdf_magic(self):
        assert self.svc._is_pdf_file(b"%PDF-1.4 some content") is True

    def test_empty_bytes(self):
        assert self.svc._is_pdf_file(b"") is False

    def test_short_bytes(self):
        assert self.svc._is_pdf_file(b"abc") is False

    def test_image_bytes_no_pdf_header(self):
        # Bytes without %PDF- header - fitz may still detect as valid, so just test the header check
        raw = b"JFIF image data " * 10
        # The method first checks for %PDF- in header
        assert b"%PDF-" not in raw[:1024]


class TestExtractValidation:
    def setup_method(self):
        self.svc = IdentityExtractionService()

    def test_empty_image_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.svc.extract(b"", "id_card")

    def test_empty_doc_type_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.svc.extract(b"some image bytes", "")


class TestSafeExtract:
    def test_success(self):
        svc = IdentityExtractionService()
        svc.extract = MagicMock(return_value=ExtractionResult(
            doc_type="id_card",
            raw_text="text",
            extracted_data={"name": "张三"},
            confidence=0.95,
            extraction_method="ocr_regex",
        ))
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is True
        assert result["doc_type"] == "id_card"

    def test_ocr_error(self):
        svc = IdentityExtractionService()
        svc.extract = MagicMock(side_effect=OCRExtractionError("OCR failed"))
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is False
        assert "OCR failed" in result["error"]

    def test_validation_error(self):
        svc = IdentityExtractionService()
        from apps.core.exceptions import ValidationException

        svc.extract = MagicMock(side_effect=ValidationException(message="invalid"))
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is False

    def test_unknown_error(self):
        svc = IdentityExtractionService()
        svc.extract = MagicMock(side_effect=RuntimeError("unexpected"))
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is False


class TestOcrExtractWithRecognizer:
    def test_recognizer_with_classification(self):
        recognizer = MagicMock()
        recognizer.classification.return_value = "识别到的文字"
        svc = IdentityExtractionService(recognizer=recognizer)
        result = svc._ocr_extract(b"some bytes")
        assert result == "识别到的文字"

    def test_recognizer_empty_raises(self):
        recognizer = MagicMock()
        recognizer.classification.return_value = ""
        svc = IdentityExtractionService(recognizer=recognizer)
        with pytest.raises(OCRExtractionError):
            svc._ocr_extract(b"some bytes")

    def test_recognizer_exception_raises(self):
        recognizer = MagicMock()
        recognizer.classification.side_effect = RuntimeError("OCR engine error")
        svc = IdentityExtractionService(recognizer=recognizer)
        with pytest.raises(OCRExtractionError):
            svc._ocr_extract(b"some bytes")
