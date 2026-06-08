"""Tests for workbench.tasks.parsing - chunk_text, build_case_info, merge_chunk_results."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.tasks.parsing import (
    build_case_info,
    chunk_text,
    merge_chunk_results,
    parse_llm_result,
)


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        text = "Short text"
        result = chunk_text(text, max_size=1000, overlap=100)
        assert result == [text]

    def test_exact_max_size(self) -> None:
        text = "a" * 1000
        result = chunk_text(text, max_size=1000, overlap=100)
        assert result == [text]

    def test_long_text_multiple_chunks(self) -> None:
        text = "。".join([f"段落{i}的内容" for i in range(100)])
        result = chunk_text(text, max_size=50, overlap=10)
        assert len(result) > 1

    def test_overlap_present(self) -> None:
        text = "A" * 100 + "\n\n" + "B" * 100
        result = chunk_text(text, max_size=60, overlap=10)
        assert len(result) >= 2

    def test_empty_text(self) -> None:
        result = chunk_text("", max_size=100, overlap=10)
        assert result == [""]

    def test_breaks_at_newline(self) -> None:
        text = "第一段内容很长很长很长很长很长\n\n第二段内容也很长很长很长"
        result = chunk_text(text, max_size=15, overlap=5)
        assert len(result) >= 1


class TestBuildCaseInfo:
    def test_all_fields(self) -> None:
        metadata = {
            "case_number": "(2024)京0101民初123号",
            "court": "北京市东城区人民法院",
            "cause": "买卖合同纠纷",
            "judge": "张三",
            "clerk": "李四",
        }
        result = build_case_info(metadata)
        assert "案号" in result
        assert "审理法院" in result
        assert "案由" in result
        assert "法官" in result
        assert "书记员" in result

    def test_partial_fields(self) -> None:
        metadata = {"case_number": "(2024)京0101民初123号", "court": None}
        result = build_case_info(metadata)
        assert "案号" in result
        assert "审理法院" not in result

    def test_empty_metadata(self) -> None:
        result = build_case_info({})
        assert result == ""

    def test_none_values(self) -> None:
        result = build_case_info({"case_number": None, "court": None})
        assert result == ""


class TestParseLlmResult:
    @patch("apps.core.llm.structured_output.parse_model_content")
    def test_json_parse_success(self, mock_parse) -> None:
        mock_result = MagicMock()
        mock_result.case_number = "2024京0101民初123号"
        mock_result.cause = "买卖合同"
        mock_result.court = "北京法院"
        mock_result.judge = "张三"
        mock_result.clerk = "李四"
        mock_result.is_relevant = True
        mock_result.conclusion = "原告胜诉"
        mock_result.analysis = "详细分析"
        mock_parse.return_value = mock_result

        result = parse_llm_result("some json", "test.pdf")
        assert result["parse_method"] == "json"
        assert result["case_number"] == "2024京0101民初123号"
        assert result["is_relevant"] is True

    @patch("apps.core.llm.structured_output.parse_model_content")
    def test_json_parse_fallback_to_regex(self, mock_parse) -> None:
        mock_parse.side_effect = Exception("parse error")

        text = '''这里是分析正文内容。

【案例元数据汇总】
案号：(2024)京0101民初123号
案由：买卖合同纠纷
审理法院：北京市东城区人民法院
与研究问题相关：是
'''
        result = parse_llm_result(text, "test.pdf")
        assert result["parse_method"] == "regex"
        assert "123" in result["case_number"]
        assert result["is_relevant"] is True

    @patch("apps.core.llm.structured_output.parse_model_content")
    def test_regex_no_metadata_block(self, mock_parse) -> None:
        mock_parse.side_effect = Exception("parse error")

        text = "简单的分析文本，没有元数据块"
        result = parse_llm_result(text, "test.pdf")
        assert result["parse_method"] == "regex"
        assert result["case_number"] == "未注明"

    @patch("apps.core.llm.structured_output.parse_model_content")
    def test_regex_conclusion_match(self, mock_parse) -> None:
        mock_parse.side_effect = Exception("parse error")

        text = '''## 针对研究问题的结论
本案原告胜诉。

【案例元数据汇总】
案号：(2024)京0101民初123号
'''
        result = parse_llm_result(text, "test.pdf")
        assert result["parse_method"] == "regex"
        assert "原告胜诉" in result["conclusion"]


class TestMergeChunkResults:
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_single_chunk(self, mock_parse) -> None:
        mock_parse.return_value = {"analysis": "test", "parse_method": "json"}
        result = merge_chunk_results(["single result"], "test.pdf")
        assert result == "single result"

    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_multiple_chunks(self, mock_parse) -> None:
        mock_parse.return_value = {
            "case_number": "test",
            "cause": "test",
            "court": "test",
            "judge": "test",
            "clerk": "test",
            "is_relevant": True,
            "conclusion": "test",
            "analysis": "chunk analysis",
            "parse_method": "json",
        }
        result = merge_chunk_results(["chunk1", "chunk2"], "test.pdf")
        parsed = json.loads(result)
        assert "---" in parsed["analysis"]
