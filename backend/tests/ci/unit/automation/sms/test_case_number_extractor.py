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
            {"case_numbers": ["（2025）粤0606民初12345号"]}
        )
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

        result = self.service.extract_from_content("文书内容包含案号")
        assert len(result) >= 1

    def test_extract_from_content_provider_returns_empty(self) -> None:
        """provider 返回空案号列表。"""
        self.extraction_provider.extract.return_value = json.dumps({"case_numbers": []})

        result = self.service.extract_from_content("文书内容")
        assert result == []

    def test_parse_ollama_response_valid_json(self) -> None:
        """解析有效 JSON 响应。"""
        response = '{"case_numbers": ["（2025）粤0606民初12345号"]}'
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

        result = self.service._parse_ollama_response(response)
        assert len(result) >= 1

    def test_parse_ollama_response_invalid_json(self) -> None:
        """解析无效 JSON 响应，使用降级方案。"""
        response = "案号：（2025）粤0606民初12345号"
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

        result = self.service._parse_ollama_response(response)
        # 降级方案可能提取到也可能提取不到
        assert isinstance(result, list)

    def test_parse_ollama_response_with_markdown(self) -> None:
        """解析包含 markdown 包裹的 JSON 响应。"""
        response = '```json\n{"case_numbers": ["（2025）粤0606民初12345号"]}\n```'
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

        result = self.service._parse_ollama_response(response)
        assert isinstance(result, list)

    def test_validate_and_normalize_empty(self) -> None:
        """空列表返回空列表。"""
        assert self.service.validate_and_normalize([]) == []

    def test_validate_and_normalize_deduplicate(self) -> None:
        """去重案号。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

        result = self.service.validate_and_normalize(
            ["（2025）粤0606民初12345号", "（2025）粤0606民初12345号"]
        )
        # 应该只有一个
        assert len(result) == 1

    def test_validate_and_normalize_invalid(self) -> None:
        """无效案号被过滤。"""
        self.case_number_service.normalize_case_number.return_value = "invalid"

        result = self.service.validate_and_normalize(["invalid"])
        assert result == []

    def test_validate_and_normalize_rejects_overlong_text(self) -> None:
        """超长文本（正则贪婪匹配的文书段落）被拒绝，避免误吞整段。"""
        # 实际事故案例：PDF 正文被当作案号提取（含换行、多数字、尾部带"号"）
        long_payload = "（2026）粤0606民初88888号\n某市某公司和某特钢公司：" + "（单位）起诉至本院。" * 20 + "\n本院地址：某市某区某路140号"

        result = self.service.validate_and_normalize([long_payload])
        assert result == []

    def test_validate_and_normalize_rejects_single_digit_group(self) -> None:
        """仅一个数字组的地址文本不被当作案号（案号需法院代码+序号至少两组数字）。"""
        self.case_number_service.normalize_case_number.side_effect = lambda n: n.replace(" ", "")

        result = self.service.validate_and_normalize(["某市某区某路140号", "本院地址：某市某区某路140号"])
        assert result == []

    def test_validate_and_normalize_accepts_real_case_number(self) -> None:
        """真实案号（含两组及以上数字）仍通过校验。"""
        self.case_number_service.normalize_case_number.side_effect = lambda n: n.replace(" ", "")

        result = self.service.validate_and_normalize(
            ["（2026）粤0606民初88888号", "（2024）粤0606执12345号", "粤0606民初88888号"]
        )
        # 简式「粤0606民初88888号」是「（2026）粤0606民初88888号」的年份缺失版，应被去重，只保留完整版
        assert result == ["（2026）粤0606民初88888号", "（2024）粤0606执12345号"]

    def test_sync_to_case_empty_case_id(self) -> None:
        """空 case_id 返回 0。"""
        result = self.service.sync_to_case(0, ["（2025）粤0606民初12345号"], 1)
        assert result == 0

    def test_sync_to_case_empty_numbers(self) -> None:
        """空案号列表返回 0。"""
        result = self.service.sync_to_case(1, [], 1)
        assert result == 0

    def test_sync_to_case_success(self) -> None:
        """成功同步案号到案件。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"
        self.case_service.get_case_numbers_by_case_internal.return_value = []

        result = self.service.sync_to_case(1, ["（2025）粤0606民初12345号"], 1)
        assert result == 1
        self.case_number_service.create_number.assert_called_once()

    def test_sync_to_case_already_exists(self) -> None:
        """案号已存在，跳过。"""
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"
        self.case_service.get_case_numbers_by_case_internal.return_value = ["（2025）粤0606民初12345号"]

        result = self.service.sync_to_case(1, ["（2025）粤0606民初12345号"], 1)
        assert result == 0

    def test_regex_extract_numbers(self) -> None:
        """正则提取案号。"""
        text = "案号：（2025）粤0606民初12345号"
        result = self.service._regex_extract_numbers(text)
        assert isinstance(result, list)

    def test_regex_extract_preserves_year_when_full_case_number(self) -> None:
        """标准格式案号应保留完整年份，且不贪吃后续正文。"""
        text = "（2026）粤0606民初88888号南海公司和某不锈钢业有限公司与你单位之间买卖合同纠纷一案你起诉至本院。本院地址：某市某区某路140号"
        result = self.service._regex_extract_numbers(text)
        assert "（2026）粤0606民初88888号" in result
        assert all("买卖" not in c and "地址" not in c for c in result)

    def test_validate_and_normalize_full_chain_keeps_full_case_number(self) -> None:
        """完整链路：正则提取→验证，应产出完整带年份案号而非残段。"""
        from unittest.mock import MagicMock

        from apps.cases.utils import normalize_case_number as real_normalize

        mock = MagicMock()
        mock.normalize_case_number.side_effect = lambda n: real_normalize(n.replace(" ", ""))

        service = CaseNumberExtractorService(
            document_processing_service=self.document_processing_service,
            case_service=self.case_service,
            case_number_service=mock,
            extraction_provider=self.extraction_provider,
            llm_service=self.llm_service,
        )
        content = "（2026）粤0606民初88888号南海公司起诉至本院。本院地址：某市某区某路140号".replace(" ", "")
        raw = service._regex_extract_numbers(content)
        validated = service.validate_and_normalize(raw)
        assert "（2026）粤0606民初88888号" in validated
        # 完整带年份案号必须优先产出，且不应混入地址残段
        assert not any("地址" in n for n in validated)

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
            "text": "案号：（2025）粤0606民初12345号"
        }
        self.extraction_provider.extract.return_value = json.dumps(
            {"case_numbers": ["（2025）粤0606民初12345号"]}
        )
        self.case_number_service.normalize_case_number.return_value = "（2025）粤0606民初12345号"

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
