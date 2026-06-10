"""Batch 6 coverage tests for workbench module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestWorkbenchParsing:
    def test_chunk_text_short(self):
        from apps.workbench.tasks.parsing import chunk_text

        text = "short text"
        result = chunk_text(text)
        assert result == ["short text"]

    def test_chunk_text_long(self):
        from apps.workbench.tasks.parsing import chunk_text

        text = "a" * 5000
        result = chunk_text(text, max_size=1000, overlap=200)
        assert len(result) > 1

    def test_chunk_text_with_sentence_break(self):
        from apps.workbench.tasks.parsing import chunk_text

        text = "第一段内容。\n" * 100
        result = chunk_text(text, max_size=500, overlap=50)
        assert len(result) > 1

    def test_build_case_info_full(self):
        from apps.workbench.tasks.parsing import build_case_info

        metadata = {
            "case_number": "（2023）京0108民初12345号",
            "court": "北京市海淀区人民法院",
            "cause": "合同纠纷",
            "judge": "张三",
            "clerk": "李四",
        }
        result = build_case_info(metadata)
        assert "案号" in result
        assert "法院" in result

    def test_build_case_info_empty(self):
        from apps.workbench.tasks.parsing import build_case_info

        result = build_case_info({})
        assert result == ""

    def test_build_case_info_partial(self):
        from apps.workbench.tasks.parsing import build_case_info

        metadata = {"case_number": "（2023）京0108民初12345号"}
        result = build_case_info(metadata)
        assert "案号" in result
        assert "法院" not in result

    def test_merge_chunk_results_single(self):
        from apps.workbench.tasks.parsing import merge_chunk_results

        result = merge_chunk_results(["single result"], "test.txt")
        assert result == "single result"

    def test_merge_chunk_results_multiple(self):
        from apps.workbench.tasks.parsing import merge_chunk_results

        r1 = '{"case_number": "test", "cause": "test", "court": "test", "judge": "test", "clerk": "test", "is_relevant": true, "conclusion": "c1", "analysis": "a1", "parse_method": "json"}'
        r2 = '{"case_number": "test", "cause": "test", "court": "test", "judge": "test", "clerk": "test", "is_relevant": true, "conclusion": "c2", "analysis": "a2", "parse_method": "json"}'
        result = merge_chunk_results([r1, r2], "test.txt")
        import json

        parsed = json.loads(result)
        assert "a1" in parsed["analysis"]
        assert "a2" in parsed["analysis"]


class TestWorkbenchConstants:
    def test_constants(self):
        from apps.workbench.tasks.constants import (
            CHUNK_OVERLAP,
            CHUNK_SIZE,
            CHUNK_THRESHOLD,
            PROGRESS_UPDATE_EVERY,
        )

        assert CHUNK_SIZE > 0
        assert CHUNK_OVERLAP > 0
        assert CHUNK_THRESHOLD > CHUNK_SIZE
        assert PROGRESS_UPDATE_EVERY > 0

    def test_case_analysis_result_model(self):
        from apps.workbench.tasks.constants import CaseAnalysisResult

        result = CaseAnalysisResult()
        assert result.case_number == "未注明"
        assert result.is_relevant is True
        assert result.conclusion == ""
