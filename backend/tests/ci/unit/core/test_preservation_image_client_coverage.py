"""Coverage tests for image_rotation, client extraction services."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# --- image_rotation auto_rename_service ---

class TestAutoRenameService:
    def test_extraction_result(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        result = ExtractionResult(date="20250630", amount="65500元")
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_extraction_result_defaults(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        result = ExtractionResult()
        assert result.date is None
        assert result.amount is None

    def test_rename_suggestion(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion

        result = RenameSuggestion(original_filename="test.pdf", suggested_filename="20250630_65500元.pdf")
        assert result.success is True
        assert result.error is None

    def test_rename_suggestion_error(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion

        result = RenameSuggestion(
            original_filename="test.pdf", suggested_filename="test.pdf", success=False, error="failed"
        )
        assert result.success is False

    def test_extract_info_empty_text(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "qwen3:0.6b"
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            service = AutoRenameService(llm_client=MagicMock())
            result = service.extract_info("")
            assert result.date is None


# --- image_rotation api ---

class TestImageRotationApi:
    def test_validate_image_file_valid(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 1024
        _validate_image_file(file_obj)  # Should not raise

    def test_validate_image_file_invalid_type(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        file_obj = MagicMock()
        file_obj.content_type = "application/pdf"
        file_obj.size = 1024
        with pytest.raises(Exception):  # noqa: B017
            _validate_image_file(file_obj)

    def test_validate_image_file_too_large(self):
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        file_obj = MagicMock()
        file_obj.content_type = "image/jpeg"
        file_obj.size = 21 * 1024 * 1024
        with pytest.raises(Exception):  # noqa: B017
            _validate_image_file(file_obj)


# --- client identity_extraction ---

class TestIdentityExtractionService:
    def test_init(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService(recognizer=MagicMock())
        assert service._recognizer is not None

    def test_extract_empty_bytes(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        with pytest.raises(Exception):  # noqa: B017
            service.extract(b"", "id_card")

    def test_extract_empty_doc_type(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        with pytest.raises(Exception):  # noqa: B017
            service.extract(b"some image data", "")

    def test_is_pdf_file(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._is_pdf_file(b"%PDF-1.4 test data") is True
        assert service._is_pdf_file(b"PNG image data") is False
        assert service._is_pdf_file(b"") is False

    def test_looks_like_json_noise(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._looks_like_json_noise('{"key": "value", "another": "test"}') is True
        assert service._looks_like_json_noise("正常文字") is False
        assert service._looks_like_json_noise("ab") is False

    def test_is_meaningful_line(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._is_meaningful_line("正常内容") is True
        assert service._is_meaningful_line("") is False
        assert service._is_meaningful_line("----") is False
        assert service._is_meaningful_line("aaaa") is False

    def test_prepare_text_for_llm(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._prepare_text_for_llm("第一行\n第二行\n\n第三行")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_resolve_doc_type_business_license(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._resolve_doc_type("auto", "营业执照\n统一社会信用代码")
        assert result == "business_license"

    def test_resolve_doc_type_id_card(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._resolve_doc_type("auto", "公民身份号码 居民身份证 姓名")
        assert result == "id_card"

    def test_resolve_doc_type_explicit(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._resolve_doc_type("business_license", "任何文字")
        assert result == "business_license"

    def test_extract_id_number(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._extract_id_number("公民身份号码 000000000000000000")
        assert result == "000000000000000000"

    def test_extract_id_number_none(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._extract_id_number("没有身份证号") is None

    def test_extract_name(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._extract_name(["姓名：张三"])
        assert result == "张三"

    def test_extract_gender(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._extract_gender(["性别：男"]) == "男"

    def test_extract_ethnicity(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._extract_ethnicity(["民族：汉"]) == "汉"

    def test_format_date_parts(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._format_date_parts("2025", "06", "30") == "2025-06-30"
        assert service._format_date_parts("abc", "1", "1") is None
        assert service._format_date_parts("2025", "13", "01") is None

    def test_extract_business_license(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        text = "统一社会信用代码：91440101MA5D123456\n法定代表人：张三\n地址：广州市天河区"
        result = service._extract_business_license(text)
        assert result is not None
        assert result.get("credit_code") is not None

    def test_extract_by_rules_business_license(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._extract_by_rules("统一社会信用代码 91440101MA5D123456", "business_license")
        assert result is not None

    def test_extract_by_rules_unsupported(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        assert service._extract_by_rules("text", "passport") is None

    def test_parse_llm_json_code_block(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        result = IdentityExtractionService._parse_llm_json('```json\n{"key": "value"}\n```')
        assert result["key"] == "value"

    def test_parse_llm_json_direct(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        result = IdentityExtractionService._parse_llm_json('{"name": "test"}')
        assert result["name"] == "test"

    def test_parse_llm_json_failure(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        with pytest.raises(ValueError):
            IdentityExtractionService._parse_llm_json("no json here")

    def test_extract_expiry_date(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._extract_expiry_date(["有效期限：2020-01-01 至 长期"])
        assert result == "2099-12-31"

    def test_extract_birth_date(self):
        from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

        service = IdentityExtractionService()
        result = service._extract_birth_date("出生：1990年01月01日", None)
        assert result == "1990-01-01"
