"""证件信息提取服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService


class TestIdentityExtractionServiceTextProcessing:
    """文本清洗与预处理测试。"""

    def _make_service(self):
        return IdentityExtractionService(recognizer=None)

    # ── _is_pdf_file ──

    def test_is_pdf_file_empty_bytes(self):
        svc = self._make_service()
        assert svc._is_pdf_file(b"") is False

    def test_is_pdf_file_short_bytes(self):
        svc = self._make_service()
        assert svc._is_pdf_file(b"abc") is False

    def test_is_pdf_file_with_magic_bytes(self):
        svc = self._make_service()
        data = b"%PDF-1.4 some content here"
        assert svc._is_pdf_file(data) is True

    def test_is_pdf_file_with_bom_then_pdf(self):
        svc = self._make_service()
        data = b"\xef\xbb\xbf%PDF-1.4 content"
        assert svc._is_pdf_file(data) is True

    @patch("fitz.open")
    def test_is_pdf_file_image_bytes(self, mock_fitz):
        mock_fitz.side_effect = Exception("not a pdf")
        svc = self._make_service()
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert svc._is_pdf_file(data) is False

    # ── _looks_like_json_noise ──

    def test_looks_like_json_noise_short_line(self):
        svc = self._make_service()
        assert svc._looks_like_json_noise("hello") is False

    def test_looks_like_json_noise_json_object(self):
        svc = self._make_service()
        assert svc._looks_like_json_noise('{"key": "value", "num": 123}') is True

    def test_looks_like_json_noise_json_array(self):
        svc = self._make_service()
        assert svc._looks_like_json_noise('[{"a": 1}]') is True

    def test_looks_like_json_noise_key_value_pattern(self):
        svc = self._make_service()
        assert svc._looks_like_json_noise('"name": "test_value_here"') is True

    def test_looks_like_json_noise_high_ratio(self):
        svc = self._make_service()
        line = '{"key":"' + 'x' * 20 + '"}'
        assert svc._looks_like_json_noise(line) is True

    def test_looks_like_json_noise_normal_text(self):
        svc = self._make_service()
        assert svc._looks_like_json_noise("这是一段普通的OCR文字内容") is False

    # ── _is_meaningful_line ──

    def test_is_meaningful_line_empty(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("") is False

    def test_is_meaningful_line_separator(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("----") is False

    def test_is_meaningful_line_equals(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("====") is False

    def test_is_meaningful_line_repeated_chars(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("11111111") is False

    def test_is_meaningful_line_json_noise(self):
        svc = self._make_service()
        assert svc._is_meaningful_line('{"key": "value"}') is False

    def test_is_meaningful_line_single_symbol(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("。") is False

    def test_is_meaningful_line_chinese_text(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("姓名：张三") is True

    def test_is_meaningful_line_digit(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("5") is True

    def test_is_meaningful_line_letter(self):
        svc = self._make_service()
        assert svc._is_meaningful_line("A") is True

    # ── _prepare_text_for_llm ──

    def test_prepare_text_for_llm_deduplicates(self):
        svc = self._make_service()
        text = "姓名：张三\n姓名：张三\n性别：男"
        result = svc._prepare_text_for_llm(text)
        assert result.count("姓名：张三") == 1

    def test_prepare_text_for_llm_removes_empty_lines(self):
        svc = self._make_service()
        text = "姓名：张三\n\n\n性别：男"
        result = svc._prepare_text_for_llm(text)
        assert "\n\n" not in result

    def test_prepare_text_for_llm_removes_json_noise(self):
        svc = self._make_service()
        text = '姓名：张三\n{"key": "value"}\n性别：男'
        result = svc._prepare_text_for_llm(text)
        assert "key" not in result

    def test_prepare_text_for_llm_pipe_separator(self):
        svc = self._make_service()
        text = "姓名：张三|性别：男"
        result = svc._prepare_text_for_llm(text)
        assert "姓名：张三" in result
        assert "性别：男" in result

    def test_prepare_text_for_llm_all_noise_returns_fallback(self):
        svc = self._make_service()
        text = "====\n----\n1111"
        result = svc._prepare_text_for_llm(text)
        # Should fallback to raw text
        assert len(result) > 0

    # ── _extract_id_number ──

    def test_extract_id_number_valid(self):
        svc = self._make_service()
        text = "公民身份号码 440106199001011234"  # allowlist secret
        assert svc._extract_id_number(text) == "440106199901011234" or svc._extract_id_number(text) == "440106199001011234"  # allowlist secret

    def test_extract_id_number_with_x(self):
        svc = self._make_service()
        text = "公民身份号码 44010619900101123X"  # allowlist secret
        result = svc._extract_id_number(text)
        assert result is not None
        assert result.endswith("X")

    def test_extract_id_number_none(self):
        svc = self._make_service()
        assert svc._extract_id_number("没有身份证号") is None

    # ── _extract_name ──

    def test_extract_name_found(self):
        svc = self._make_service()
        assert svc._extract_name(["姓名：张三"]) == "张三"

    def test_extract_name_with_dot(self):
        svc = self._make_service()
        assert svc._extract_name(["姓名：张·三"]) == "张·三"

    def test_extract_name_not_found(self):
        svc = self._make_service()
        assert svc._extract_name(["地址：北京"]) is None

    # ── _extract_gender ──

    def test_extract_gender_male(self):
        svc = self._make_service()
        assert svc._extract_gender(["性别：男"]) == "男"

    def test_extract_gender_female(self):
        svc = self._make_service()
        assert svc._extract_gender(["性别:女"]) == "女"

    def test_extract_gender_not_found(self):
        svc = self._make_service()
        assert svc._extract_gender(["姓名：张三"]) is None

    # ── _extract_ethnicity ──

    def test_extract_ethnicity_han(self):
        svc = self._make_service()
        assert svc._extract_ethnicity(["民族：汉"]) == "汉"

    def test_extract_ethnicity_not_found(self):
        svc = self._make_service()
        assert svc._extract_ethnicity(["姓名：张三"]) is None

    # ── _format_date_parts ──

    def test_format_date_parts_valid(self):
        svc = self._make_service()
        assert svc._format_date_parts("2025", "1", "15") == "2025-01-15"

    def test_format_date_parts_zero_month(self):
        svc = self._make_service()
        assert svc._format_date_parts("2025", "0", "15") is None

    def test_format_date_parts_negative_day(self):
        svc = self._make_service()
        assert svc._format_date_parts("2025", "1", "-1") is None

    def test_format_date_parts_invalid_year(self):
        svc = self._make_service()
        assert svc._format_date_parts("1800", "1", "1") is None

    def test_format_date_parts_month_13(self):
        svc = self._make_service()
        assert svc._format_date_parts("2025", "13", "1") is None

    def test_format_date_parts_day_32(self):
        svc = self._make_service()
        assert svc._format_date_parts("2025", "1", "32") is None

    # ── _extract_birth_date ──

    def test_extract_birth_date_from_text(self):
        svc = self._make_service()
        text = "出生：1990年01月15日"
        assert svc._extract_birth_date(text, None) == "1990-01-15"

    def test_extract_birth_date_from_id_number(self):
        svc = self._make_service()
        assert svc._extract_birth_date("", "440106199001151234") == "1990-01-15"  # allowlist secret

    def test_extract_birth_date_none(self):
        svc = self._make_service()
        assert svc._extract_birth_date("", None) is None

    # ── _extract_expiry_date ──

    def test_extract_expiry_date_long_term(self):
        svc = self._make_service()
        lines = ["有效期限：长期"]
        assert svc._extract_expiry_date(lines) == "2099-12-31"

    def test_extract_expiry_date_range(self):
        svc = self._make_service()
        lines = ["有效期限：2020年01月01日至2030年12月31日"]
        result = svc._extract_expiry_date(lines)
        assert result is not None  # should extract some date from the range

    def test_extract_expiry_date_until(self):
        svc = self._make_service()
        lines = ["有效期至：2030年12月31日"]
        result = svc._extract_expiry_date(lines)
        assert result == "2030-12-31"

    def test_extract_expiry_date_not_found(self):
        svc = self._make_service()
        assert svc._extract_expiry_date(["姓名：张三"]) is None

    # ── _extract_address ──

    def test_extract_address_found(self):
        svc = self._make_service()
        lines = ["住址", "广东省广州市天河区", "公民身份号码 440106199001011234"]  # allowlist secret
        result = svc._extract_address(lines)
        assert "广东省广州市天河区" in result

    def test_extract_address_inline(self):
        svc = self._make_service()
        lines = ["住址：广东省广州市天河区", "公民身份号码 440106199001011234"]  # allowlist secret
        result = svc._extract_address(lines)
        assert "广东省广州市天河区" in result

    def test_extract_address_none(self):
        svc = self._make_service()
        lines = ["姓名：张三", "性别：男"]
        assert svc._extract_address(lines) is None

    # ── _parse_llm_json ──

    def test_parse_llm_json_code_block(self):
        svc = self._make_service()
        content = '```json\n{"name": "张三"}\n```'
        result = svc._parse_llm_json(content)
        assert result["name"] == "张三"

    def test_parse_llm_json_plain_code_block(self):
        svc = self._make_service()
        content = '```\n{"name": "张三"}\n```'
        result = svc._parse_llm_json(content)
        assert result["name"] == "张三"

    def test_parse_llm_json_direct(self):
        svc = self._make_service()
        content = '{"name": "张三"}'
        result = svc._parse_llm_json(content)
        assert result["name"] == "张三"

    def test_parse_llm_json_embedded(self):
        svc = self._make_service()
        content = 'Some text before\n{"name": "张三"}\nSome text after'
        result = svc._parse_llm_json(content)
        assert result["name"] == "张三"

    def test_parse_llm_json_no_json_raises(self):
        svc = self._make_service()
        with pytest.raises(ValueError):
            svc._parse_llm_json("no json here at all")

    # ── _resolve_doc_type ──

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_resolve_doc_type_explicit(self):
        svc = self._make_service()
        assert svc._resolve_doc_type("id_card", "some text") == "id_card"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_resolve_doc_type_auto_business_license(self):
        svc = self._make_service()
        text = "统一社会信用代码 91440101MA5D12345X 企业名称 广州测试有限公司"
        result = svc._resolve_doc_type("auto", text)
        assert result == "business_license"

    @patch("apps.client.services.identity_extraction.extraction_service.PROMPT_MAPPING", {"id_card": "...", "business_license": "..."})
    def test_resolve_doc_type_auto_id_card(self):
        svc = self._make_service()
        text = "公民身份号码 姓名 性别 民族 住址"
        result = svc._resolve_doc_type("auto", text)
        assert result == "id_card"

    # ── _extract_business_license ──

    def test_extract_business_license_all_fields(self):
        svc = self._make_service()
        text = "公司名称：广州测试有限公司\n统一社会信用代码：91440101MA5D12345X\n法定代表人：张三\n地址：广州市天河区\n经营范围：法律服务"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["credit_code"] == "91440101MA5D12345X"
        assert result["legal_representative"] == "张三"
        assert "广州测试有限公司" in (result["company_name"] or "")

    def test_extract_business_license_none_fields(self):
        svc = self._make_service()
        text = "随机文字没有任何有用信息"
        result = svc._extract_business_license(text)
        assert result is None

    def test_extract_business_license_phone(self):
        svc = self._make_service()
        text = "联系电话：020-12345678\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["phone"] is not None

    def test_extract_business_license_registration_date(self):
        svc = self._make_service()
        text = "成立日期：2020年01月15日\n统一社会信用代码：91440101MA5D12345X"
        result = svc._extract_business_license(text)
        assert result is not None
        assert result["registration_date"] == "2020-01-15"

    # ── safe_extract ──

    @patch.object(IdentityExtractionService, "extract")
    def test_safe_extract_success(self, mock_extract):
        svc = self._make_service()
        mock_extract.return_value = MagicMock(
            doc_type="id_card",
            extracted_data={"name": "张三"},
            confidence=0.95,
        )
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is True
        assert result["extracted_data"]["name"] == "张三"

    @patch.object(IdentityExtractionService, "extract")
    def test_safe_extract_ocr_error(self, mock_extract):
        from apps.client.services.identity_extraction.data_classes import OCRExtractionError

        svc = self._make_service()
        mock_extract.side_effect = OCRExtractionError("OCR失败")
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is False
        assert "OCR" in result["error"]

    @patch.object(IdentityExtractionService, "extract")
    def test_safe_extract_validation_error(self, mock_extract):
        from apps.core.exceptions import ValidationException

        svc = self._make_service()
        mock_extract.side_effect = ValidationException(message="test", code="TEST", errors={})
        result = svc.safe_extract(b"image", "id_card")
        assert result["success"] is False
