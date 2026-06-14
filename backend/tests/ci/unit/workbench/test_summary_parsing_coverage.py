"""Coverage tests for workbench/tasks/summary.py and parsing.py."""
from __future__ import annotations

import csv
import io
import zipfile
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID

import pytest


class TestChunkText:
    def test_short_text(self):
        from apps.workbench.tasks.parsing import chunk_text

        result = chunk_text("short text")
        assert result == ["short text"]

    def test_long_text_chunks(self):
        from apps.workbench.tasks.parsing import chunk_text

        text = "A" * 30000
        result = chunk_text(text, max_size=15000, overlap=2000)
        assert len(result) >= 2

    def test_breaks_at_separator(self):
        from apps.workbench.tasks.parsing import chunk_text

        text = "A" * 7500 + "\n\n" + "B" * 7500
        result = chunk_text(text, max_size=15000, overlap=2000)
        assert len(result) >= 1


class TestBuildCaseInfo:
    def test_all_fields(self):
        from apps.workbench.tasks.parsing import build_case_info

        metadata = {
            "case_number": "（2024）京01民初123号",
            "court": "北京一中院",
            "cause": "合同纠纷",
            "judge": "张三",
            "clerk": "李四",
        }
        result = build_case_info(metadata)
        assert "案号" in result
        assert "北京一中院" in result

    def test_empty_metadata(self):
        from apps.workbench.tasks.parsing import build_case_info

        result = build_case_info({})
        assert result == ""


class TestMergeChunkResults:
    def test_single_chunk(self):
        from apps.workbench.tasks.parsing import merge_chunk_results

        result = merge_chunk_results(["single result"], "test.pdf")
        assert result == "single result"

    def test_multiple_chunks(self):
        from apps.workbench.tasks.parsing import merge_chunk_results

        with patch("apps.workbench.tasks.parsing.parse_llm_result") as mock_parse:
            parsed = {"analysis": "分析内容", "case_number": "test", "cause": "", "court": "", "judge": "", "clerk": "", "is_relevant": True, "conclusion": "结论", "parse_method": "json"}
            mock_parse.return_value = parsed
            result = merge_chunk_results(["result1", "result2"], "test.pdf")
            assert "分析内容" in result


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_empty_items(self):
        from apps.workbench.tasks.summary import generate_summary

        job_id = UUID("12345678-1234-5678-1234-567812345678")
        result = await generate_summary(job_id, "test prompt", [])
        assert "无法生成汇总" in result

    @pytest.mark.asyncio
    async def test_with_completed_items(self):
        from apps.workbench.tasks.summary import generate_summary

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        item1 = MagicMock()
        item1.result = '{"case_number": "test", "cause": "合同", "court": "法院", "judge": "法官", "clerk": "书记员", "is_relevant": true, "conclusion": "结论", "analysis": "分析"}'
        item1.file_name = "file1.pdf"

        with patch("apps.workbench.tasks.summary.parse_llm_result") as mock_parse:
            mock_parse.return_value = {
                "case_number": "test", "cause": "合同", "court": "法院",
                "judge": "法官", "clerk": "书记员", "is_relevant": True,
                "conclusion": "结论", "analysis": "分析", "parse_method": "json",
            }
            with patch("apps.workbench.tasks.summary.sync_to_async") as mock_sta:
                mock_sta.return_value = AsyncMock()

                result = await generate_summary(job_id, "分析合同", [item1])
                assert "案例分析汇总" in result
                assert "相关案例：1" in result

    @pytest.mark.asyncio
    async def test_regex_fallback_items(self):
        from apps.workbench.tasks.summary import generate_summary

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        item = MagicMock()
        item.result = "some text"
        item.file_name = "file.pdf"

        with patch("apps.workbench.tasks.summary.parse_llm_result") as mock_parse:
            mock_parse.return_value = {
                "case_number": "未注明", "cause": "未注明", "court": "未注明",
                "judge": "未注明", "clerk": "未注明", "is_relevant": True,
                "conclusion": "未注明", "analysis": "", "parse_method": "regex",
            }
            with patch("apps.workbench.tasks.summary.sync_to_async") as mock_sta:
                mock_sta.return_value = AsyncMock()

                result = await generate_summary(job_id, "分析", [item])
                assert "未提取到元数据：1" in result


class TestBuildDetailZipSync:
    def test_no_completed_items(self):
        from apps.workbench.tasks.summary import build_detail_zip_sync

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        with patch("apps.workbench.tasks.summary.BatchJobItem") as mock_model:
            mock_model.objects.filter.return_value = []
            result = build_detail_zip_sync(job_id)
            assert result is False

    def test_with_completed_items(self):
        from apps.workbench.tasks.summary import build_detail_zip_sync

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        item = MagicMock()
        item.result = '{"case_number": "test", "cause": "合同", "court": "法院", "judge": "法官", "clerk": "书记员", "is_relevant": true, "conclusion": "结论", "analysis": "分析内容"}'
        item.file_name = "test_file.pdf"

        with patch("apps.workbench.tasks.summary.BatchJobItem") as mock_item_model:
            mock_item_model.objects.filter.return_value = [item]

            with patch("apps.workbench.tasks.summary.parse_llm_result") as mock_parse:
                mock_parse.return_value = {
                    "case_number": "test", "cause": "合同", "court": "法院",
                    "judge": "法官", "clerk": "书记员", "is_relevant": True,
                    "conclusion": "结论", "analysis": "分析内容", "parse_method": "json",
                }

                with patch("apps.workbench.tasks.summary.BatchJob") as mock_job_model:
                    mock_job = MagicMock()
                    mock_job_model.objects.get.return_value = mock_job

                    result = build_detail_zip_sync(job_id)
                    assert result is True
                    mock_job.detail_zip_file.save.assert_called_once()

    def test_with_no_result_item(self):
        from apps.workbench.tasks.summary import build_detail_zip_sync

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        item = MagicMock()
        item.result = None
        item.file_name = "empty.pdf"

        with patch("apps.workbench.tasks.summary.BatchJobItem") as mock_item_model:
            mock_item_model.objects.filter.return_value = [item]

            with patch("apps.workbench.tasks.summary.BatchJob") as mock_job_model:
                mock_job = MagicMock()
                mock_job_model.objects.get.return_value = mock_job

                result = build_detail_zip_sync(job_id)
                assert result is True

    def test_duplicate_filenames(self):
        from apps.workbench.tasks.summary import build_detail_zip_sync

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        items = []
        for _ in range(2):
            item = MagicMock()
            item.result = '{"case_number": "test"}'
            item.file_name = "same_name.pdf"
            items.append(item)

        with patch("apps.workbench.tasks.summary.BatchJobItem") as mock_item_model:
            mock_item_model.objects.filter.return_value = items

            with patch("apps.workbench.tasks.summary.parse_llm_result") as mock_parse:
                mock_parse.return_value = {
                    "case_number": "test", "cause": "", "court": "",
                    "judge": "", "clerk": "", "is_relevant": True,
                    "conclusion": "", "analysis": "", "parse_method": "json",
                }

                with patch("apps.workbench.tasks.summary.BatchJob") as mock_job_model:
                    mock_job = MagicMock()
                    mock_job_model.objects.get.return_value = mock_job

                    result = build_detail_zip_sync(job_id)
                    assert result is True

    def test_no_extension_filename(self):
        from apps.workbench.tasks.summary import build_detail_zip_sync

        job_id = UUID("12345678-1234-5678-1234-567812345678")

        item = MagicMock()
        item.result = '{"case_number": "test"}'
        item.file_name = "no_ext_file"

        with patch("apps.workbench.tasks.summary.BatchJobItem") as mock_item_model:
            mock_item_model.objects.filter.return_value = [item]

            with patch("apps.workbench.tasks.summary.parse_llm_result") as mock_parse:
                mock_parse.return_value = {
                    "case_number": "test", "cause": "", "court": "",
                    "judge": "", "clerk": "", "is_relevant": True,
                    "conclusion": "", "analysis": "", "parse_method": "json",
                }

                with patch("apps.workbench.tasks.summary.BatchJob") as mock_job_model:
                    mock_job = MagicMock()
                    mock_job_model.objects.get.return_value = mock_job

                    result = build_detail_zip_sync(job_id)
                    assert result is True
