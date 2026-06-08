"""测试 LLM 辅助服务 - 合同结构分析器的纯逻辑方法

覆盖: apps/contract_review/services/format_normalizer/llm_helper.py
重点: _parse_response (纯 JSON 解析逻辑)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestContractStructureAnalyzerParseResponse:
    """测试 LLM 响应 JSON 解析"""

    @patch("apps.core.llm.service.LLMService")
    def _make_analyzer(self, mock_llm: MagicMock) -> "ContractStructureAnalyzer":
        from apps.contract_review.services.format_normalizer.llm_helper import ContractStructureAnalyzer

        return ContractStructureAnalyzer()

    def test_parse_valid_json_array(self) -> None:
        analyzer = self._make_analyzer()
        text = '[{"level": 0, "prefix": "一、", "confidence": 0.9, "reason": "标题"}]'
        result = analyzer._parse_response(text)
        assert len(result) == 1
        assert result[0]["level"] == 0
        assert result[0]["prefix"] == "一、"

    def test_parse_json_with_surrounding_text(self) -> None:
        analyzer = self._make_analyzer()
        text = '以下是分析结果：\n[{"level": 1, "prefix": "", "confidence": 0.8, "reason": "正文"}]\n以上是结果。'
        result = analyzer._parse_response(text)
        assert len(result) == 1
        assert result[0]["level"] == 1

    def test_parse_multiple_items(self) -> None:
        analyzer = self._make_analyzer()
        text = '[{"level": 0, "prefix": "", "confidence": 0.9, "reason": "a"}, {"level": 1, "prefix": "", "confidence": 0.8, "reason": "b"}]'
        result = analyzer._parse_response(text)
        assert len(result) == 2

    def test_parse_line_by_line_json(self) -> None:
        analyzer = self._make_analyzer()
        text = '{"level": 0, "prefix": "", "confidence": 0.9, "reason": "a"}\n{"level": 1, "prefix": "", "confidence": 0.8, "reason": "b"}'
        result = analyzer._parse_response(text)
        assert len(result) == 2

    def test_parse_invalid_json_returns_empty(self) -> None:
        analyzer = self._make_analyzer()
        text = "这完全不是 JSON 内容"
        result = analyzer._parse_response(text)
        assert result == []

    def test_parse_empty_string(self) -> None:
        analyzer = self._make_analyzer()
        result = analyzer._parse_response("")
        assert result == []

    def test_parse_json_object_not_array(self) -> None:
        """如果返回的是 JSON 对象而非数组，应尝试提取数组"""
        analyzer = self._make_analyzer()
        text = 'some text [{"level": 0}] more text'
        result = analyzer._parse_response(text)
        assert len(result) == 1

    def test_parse_trailing_comma_in_line(self) -> None:
        """行尾逗号应被 strip 掉"""
        analyzer = self._make_analyzer()
        text = '{"level": 0},\n{"level": 1},'
        result = analyzer._parse_response(text)
        assert len(result) == 2

    def test_parse_markdown_code_block(self) -> None:
        """LLM 经常返回 markdown 代码块包裹的 JSON"""
        analyzer = self._make_analyzer()
        text = '```json\n[{"level": 0, "prefix": "", "confidence": 0.9, "reason": "r"}]\n```'
        result = analyzer._parse_response(text)
        assert len(result) == 1
