"""Unit tests for workbench.tasks.parsing — pure functions, no DB required."""

from __future__ import annotations

import json

import pytest

from apps.workbench.tasks.parsing import build_case_info, chunk_text, merge_chunk_results, parse_llm_result

# ─── chunk_text ──────────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_returns_single_chunk(self) -> None:
        text = "短文本"
        result = chunk_text(text, max_size=100)
        assert result == ["短文本"]

    def test_long_text_splits_into_chunks(self) -> None:
        text = "A" * 300
        result = chunk_text(text, max_size=100, overlap=10)
        assert len(result) > 1
        # 每个 chunk 长度不超过 max_size
        for chunk in result:
            assert len(chunk) <= 100

    def test_overlap_present(self) -> None:
        text = "A" * 200
        result = chunk_text(text, max_size=100, overlap=20)
        assert len(result) >= 2
        # 第二个 chunk 的开头应与第一个 chunk 的结尾重叠
        assert result[1][:20] == result[0][-20:]

    def test_breaks_at_newline(self) -> None:
        # 构造在中间有换行的文本
        text = "A" * 50 + "\n\n" + "B" * 50
        result = chunk_text(text, max_size=60, overlap=0)
        assert len(result) == 2
        assert "\n\n" in result[0]


# ─── parse_llm_result ────────────────────────────────────────────────────────


class TestParseLlmResult:
    def test_json_structured_output(self) -> None:
        json_output = json.dumps(
            {
                "case_number": "（2024）京01民初123号",
                "cause": "合同纠纷",
                "court": "北京市第一中级人民法院",
                "judge": "张法官",
                "clerk": "李书记员",
                "is_relevant": True,
                "conclusion": "支持原告诉请",
                "analysis": "本案系合同纠纷...",
            },
            ensure_ascii=False,
        )
        result = parse_llm_result(json_output, "test.json")
        assert result["case_number"] == "（2024）京01民初123号"
        assert result["cause"] == "合同纠纷"
        assert result["is_relevant"] is True
        assert result["parse_method"] == "json"

    def test_regex_fallback_metadata_block(self) -> None:
        text = (
            "## 分析\n\n本案分析内容...\n\n"
            "```\n"
            "【案例元数据汇总】\n"
            "案号：（2024）沪01民初456号\n"
            "案由：侵权纠纷\n"
            "审理法院：上海市第一中级人民法院\n"
            "法官：王法官\n"
            "书记员：赵书记员\n"
            "与研究问题相关：是\n"
            "结论：支持原告\n"
            "```\n"
        )
        result = parse_llm_result(text, "test.docx")
        assert result["case_number"] == "（2024）沪01民初456号"
        assert result["cause"] == "侵权纠纷"
        assert result["is_relevant"] is True
        assert result["parse_method"] == "regex"

    def test_regex_fallback_no_metadata(self) -> None:
        text = "纯分析文本，没有元数据块"
        result = parse_llm_result(text, "plain.txt")
        assert result["case_number"] == "未注明"
        assert result["parse_method"] == "regex"

    def test_json_parse_failure_falls_back_to_regex(self) -> None:
        text = "```json\n{invalid json\n```\n\n```【案例元数据汇总】\n案号：测试案号\n```"
        result = parse_llm_result(text, "bad.json")
        assert result["parse_method"] == "regex"


# ─── build_case_info ─────────────────────────────────────────────────────────


class TestBuildCaseInfo:
    def test_full_metadata(self) -> None:
        metadata = {
            "case_number": "（2024）京01民初123号",
            "court": "北京市第一中级人民法院",
            "cause": "合同纠纷",
            "judge": "张法官",
            "clerk": "李书记员",
        }
        result = build_case_info(metadata)
        assert "案号：（2024）京01民初123号" in result
        assert "审理法院：北京市第一中级人民法院" in result

    def test_empty_metadata(self) -> None:
        result = build_case_info({})
        assert result == ""

    def test_partial_metadata(self) -> None:
        metadata = {"case_number": "（2024）京01民初123号", "court": None}
        result = build_case_info(metadata)
        assert "案号" in result
        assert "审理法院" not in result


# ─── merge_chunk_results ─────────────────────────────────────────────────────


class TestMergeChunkResults:
    def test_single_chunk_returns_as_is(self) -> None:
        single = json.dumps({"analysis": "单段分析", "case_number": "测试"}, ensure_ascii=False)
        result = merge_chunk_results([single], "test.txt")
        assert result == single

    def test_multiple_chunks_merges_analysis(self) -> None:
        chunk1 = json.dumps(
            {"analysis": "第一段分析", "case_number": "测试", "conclusion": "结论"},
            ensure_ascii=False,
        )
        chunk2 = json.dumps(
            {"analysis": "第二段分析", "case_number": "测试", "conclusion": "最终结论"},
            ensure_ascii=False,
        )
        result = merge_chunk_results([chunk1, chunk2], "test.txt")
        parsed = json.loads(result)
        assert "第一段分析" in parsed["analysis"]
        assert "第二段分析" in parsed["analysis"]
        assert "---" in parsed["analysis"]
