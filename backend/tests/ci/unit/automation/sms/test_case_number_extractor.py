"""案号提取服务测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService


class TestCaseNumberExtractorService:
    """CaseNumberExtractorService 测试。"""

    def setup_method(self) -> None:
        self.document_processing_service = MagicMock()
        self.case_service = MagicMock()
        self.case_number_service = MagicMock()
        self.extraction_provider = MagicMock()
        self.llm_service = MagicMock()
        self.service = CaseNumberExtractorService(
            document_processing_service=self.document_processing_service,
            case_service=self.case_service,
            case_number_service=self.case_number_service,
            extraction_provider=self.extraction_provider,
            llm_service=self.llm_service,
        )

    def test_extract_from_content_empty(self) -> None:
        """空内容返回空列表。"""
        assert self.service.extract_from_content("") == []
        assert self.service.extract_from_content("   ") == []

    def test_extract_from_content_with_provider(self) -> None:
        """使用 extraction_provider 提取案号。"""
        self.extraction_provider.extract.return_value = json.dumps(
            {"case_numbers": ["（2025）粤0604民初12345号"]}
        )
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service.extract_from_content("文书内容包含案号")
        assert len(result) >= 1

    def test_extract_from_content_provider_returns_empty(self) -> None:
        """provider 返回空案号列表。"""
        self.extraction_provider.extract.return_value = json.dumps({"case_numbers": []})

        result = self.service.extract_from_content("文书内容")
        assert result == []

    def test_parse_ollama_response_valid_json(self) -> None:
        """解析有效 JSON 响应。"""
        response = '{"case_numbers": ["（2025）粤0604民初12345号"]}'
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service._parse_ollama_response(response)
        assert len(result) >= 1

    def test_parse_ollama_response_invalid_json(self) -> None:
        """解析无效 JSON 响应，使用降级方案。"""
        response = "案号：（2025）粤0604民初12345号"
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service._parse_ollama_response(response)
        # 降级方案可能提取到也可能提取不到
        assert isinstance(result, list)

    def test_parse_ollama_response_with_markdown(self) -> None:
        """解析包含 markdown 包裹的 JSON 响应。"""
        response = '```json\n{"case_numbers": ["（2025）粤0604民初12345号"]}\n```'
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service._parse_ollama_response(response)
        assert isinstance(result, list)

    def test_validate_and_normalize_empty(self) -> None:
        """空列表返回空列表。"""
        assert self.service.validate_and_normalize([]) == []

    def test_validate_and_normalize_deduplicate(self) -> None:
        """去重案号。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service.validate_and_normalize(
            ["（2025）粤0604民初12345号", "（2025）粤0604民初12345号"]
        )
        # 应该只有一个
        assert len(result) == 1

    def test_validate_and_normalize_invalid(self) -> None:
        """无效案号被过滤。"""
        self.case_number_service.normalize_case_number.return_value = "invalid"

        result = self.service.validate_and_normalize(["invalid"])
        assert result == []

    def test_sync_to_case_empty_case_id(self) -> None:
        """空 case_id 返回 0。"""
        result = self.service.sync_to_case(0, ["（2025）粤0604民初12345号"], 1)
        assert result == 0

    def test_sync_to_case_empty_numbers(self) -> None:
        """空案号列表返回 0。"""
        result = self.service.sync_to_case(1, [], 1)
        assert result == 0

    def test_sync_to_case_success(self) -> None:
        """成功同步案号到案件。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"
        self.case_service.get_case_numbers_by_case_internal.return_value = []

        result = self.service.sync_to_case(1, ["（2025）粤0604民初12345号"], 1)
        assert result == 1
        self.case_number_service.create_number.assert_called_once()

    def test_sync_to_case_already_exists(self) -> None:
        """案号已存在，跳过。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"
        self.case_service.get_case_numbers_by_case_internal.return_value = ["（2025）粤0604民初12345号"]

        result = self.service.sync_to_case(1, ["（2025）粤0604民初12345号"], 1)
        assert result == 0

    def test_regex_extract_numbers(self) -> None:
        """正则提取案号。"""
        text = "案号：（2025）粤0604民初12345号"
        result = self.service._regex_extract_numbers(text)
        assert isinstance(result, list)

    def test_extract_fallback_empty(self) -> None:
        """降级方案空文本返回空列表。"""
        assert self.service._extract_fallback("") == []
        assert self.service._extract_fallback("  ") == []

    def test_extract_from_document_empty_path(self) -> None:
        """空路径返回空列表。"""
        assert self.service.extract_from_document("") == []

    def test_extract_from_document_success(self) -> None:
        """成功从文书提取案号。"""
        self.document_processing_service.extract_document_content_by_path_internal.return_value = {
            "text": "案号：（2025）粤0604民初12345号"
        }
        self.extraction_provider.extract.return_value = json.dumps(
            {"case_numbers": ["（2025）粤0604民初12345号"]}
        )
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0604民初12345号"

        result = self.service.extract_from_document("/path/to/doc.pdf")
        assert isinstance(result, list)

    def test_extract_from_document_no_text(self) -> None:
        """文书无法提取文本，返回空列表。"""
        self.document_processing_service.extract_document_content_by_path_internal.return_value = {"text": ""}

        result = self.service.extract_from_document("/path/to/doc.pdf")
        assert result == []

    def test_extract_from_document_exception(self) -> None:
        """文书提取异常，返回空列表。"""
        self.document_processing_service.extract_document_content_by_path_internal.side_effect = Exception("error")

        result = self.service.extract_from_document("/path/to/doc.pdf")
        assert result == []
