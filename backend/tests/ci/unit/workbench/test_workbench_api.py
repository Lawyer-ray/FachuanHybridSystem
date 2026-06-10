"""Tests for workbench API module - schemas and utility functions."""

import csv
import io
import zipfile
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest


class TestGenerateFilteredCsv:
    def _make_item(self, file_name, result_text):
        item = MagicMock()
        item.file_name = file_name
        item.result = result_text
        return item

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_basic_csv_generation(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_csv

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        item = self._make_item("test.pdf", "result")
        mock_batch.get_completed_items.return_value = [item]

        mock_parse.return_value = {
            "case_number": "（2025）京01民初1号",
            "cause": "借贷纠纷",
            "court": "北京一中院",
            "judge": "张法官",
            "clerk": "李书记员",
            "is_relevant": True,
            "conclusion": "支持原告诉讼请求",
            "analysis": "详细分析内容",
            "parse_method": "llm",
        }

        job_id = uuid4()
        result = _generate_filtered_csv(job_id, only_relevant=True)

        assert isinstance(result, str)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["案号"] == "（2025）京01民初1号"

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_csv_filters_irrelevant(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_csv

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        item = self._make_item("test.pdf", "result")
        mock_batch.get_completed_items.return_value = [item]

        mock_parse.return_value = {
            "case_number": "未注明",
            "cause": "",
            "court": "",
            "judge": "",
            "clerk": "",
            "is_relevant": False,
            "conclusion": "未注明",
            "analysis": "",
            "parse_method": "regex",
        }

        result = _generate_filtered_csv(uuid4(), only_relevant=True)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_csv_includes_all_when_not_filtered(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_csv

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        item = self._make_item("test.pdf", "result")
        mock_batch.get_completed_items.return_value = [item]

        mock_parse.return_value = {
            "case_number": "未注明",
            "cause": "",
            "court": "",
            "judge": "",
            "clerk": "",
            "is_relevant": False,
            "conclusion": "未注明",
            "analysis": "",
            "parse_method": "regex",
        }

        result = _generate_filtered_csv(uuid4(), only_relevant=False)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    def test_csv_empty_items(self, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_csv

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch
        mock_batch.get_completed_items.return_value = []

        result = _generate_filtered_csv(uuid4(), only_relevant=False)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_csv_skips_null_result(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_csv

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        item = MagicMock()
        item.file_name = "test.pdf"
        item.result = None
        mock_batch.get_completed_items.return_value = [item]

        result = _generate_filtered_csv(uuid4(), only_relevant=False)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0


class TestGenerateFilteredZip:
    def _make_item(self, file_name, result_text):
        item = MagicMock()
        item.file_name = file_name
        item.result = result_text
        return item

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_basic_zip_generation(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_zip

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        item = self._make_item("test.pdf", "result")
        mock_batch.get_completed_items.return_value = [item]

        mock_parse.return_value = {
            "case_number": "（2025）京01民初1号",
            "cause": "借贷",
            "court": "法院",
            "judge": "法官",
            "clerk": "书记员",
            "is_relevant": True,
            "conclusion": "结论",
            "analysis": "分析",
            "parse_method": "llm",
        }

        result = _generate_filtered_zip(uuid4(), only_relevant=True)

        assert isinstance(result, bytes)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
            assert len(names) >= 1
            content = zf.read(names[0]).decode("utf-8")
            assert "案例分析报告" in content

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    @patch("apps.workbench.tasks.parsing.parse_llm_result")
    def test_zip_deduplicates_names(self, mock_parse, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_zip

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch

        items = [
            self._make_item("same_name.pdf", "r1"),
            self._make_item("same_name.pdf", "r2"),
        ]
        mock_batch.get_completed_items.return_value = items

        mock_parse.return_value = {
            "case_number": "号",
            "cause": "",
            "court": "",
            "judge": "",
            "clerk": "",
            "is_relevant": True,
            "conclusion": "c",
            "analysis": "a",
            "parse_method": "llm",
        }

        result = _generate_filtered_zip(uuid4(), only_relevant=False)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
            assert len(names) == 2
            assert names[0] != names[1]

    @patch("apps.workbench.api.workbench_api.ServiceLocator")
    def test_zip_empty_items(self, mock_locator):
        from apps.workbench.api.workbench_api import _generate_filtered_zip

        mock_batch = MagicMock()
        mock_locator.get_workbench_batch_service.return_value = mock_batch
        mock_batch.get_completed_items.return_value = []

        result = _generate_filtered_zip(uuid4(), only_relevant=False)

        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert len(zf.namelist()) == 0


class TestSchemas:
    def test_feedback_in_good(self):
        from apps.workbench.api.workbench_api import FeedbackIn

        fb = FeedbackIn(rating="good", comment="great")
        assert fb.rating == "good"
        assert fb.comment == "great"

    def test_feedback_in_bad(self):
        from apps.workbench.api.workbench_api import FeedbackIn

        fb = FeedbackIn(rating="bad")
        assert fb.rating == "bad"
        assert fb.comment == ""

    def test_approval_in(self):
        from apps.workbench.api.workbench_api import ApprovalIn

        ai = ApprovalIn(approval_id="abc123", approved=True)
        assert ai.approval_id == "abc123"
        assert ai.approved is True

    def test_optimize_prompt_in(self):
        from apps.workbench.api.workbench_api import OptimizePromptIn

        obj = OptimizePromptIn(prompt="分析借贷纠纷")
        assert obj.prompt == "分析借贷纠纷"

    def test_optimize_prompt_out(self):
        from apps.workbench.api.workbench_api import OptimizePromptOut

        obj = OptimizePromptOut(optimized_prompt="优化后的prompt")
        assert obj.optimized_prompt == "优化后的prompt"

    def test_batch_message_item_in(self):
        from apps.workbench.api.workbench_api import BatchMessageItemIn

        obj = BatchMessageItemIn(file_name="test.pdf", content="内容", metadata={"key": "value"})
        assert obj.file_name == "test.pdf"
        assert obj.content == "内容"
        assert obj.metadata == {"key": "value"}

    def test_batch_message_item_in_default_metadata(self):
        from apps.workbench.api.workbench_api import BatchMessageItemIn

        obj = BatchMessageItemIn(file_name="test.pdf", content="内容")
        assert obj.metadata == {}
