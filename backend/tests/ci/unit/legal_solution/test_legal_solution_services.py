"""Tests for legal_solution services."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestMdToHtml:
    def test_bold(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_ordered_list(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("1. 第一项\n2. 第二项")
        assert "<ol>" in result
        assert "<li>" in result

    def test_unordered_list(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("- 项目一\n- 项目二")
        assert "<ul>" in result

    def test_plain_text(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("普通文本")
        assert "<p>普通文本</p>" in result

    def test_empty(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("")
        assert result == ""

    def test_mixed_content(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        text = "**标题**\n\n正文内容\n\n1. 列表项"
        result = _md_to_html(text)
        assert "<strong>" in result
        assert "<p>" in result


class TestSolutionGeneratorLoadResearchResults:
    def test_no_research_task(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        task.research_task_id = None
        assert SolutionGenerator._load_research_results(task) == ""


class TestSolutionGeneratorGetExistingSections:
    def test_returns_dict(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exclude.return_value = mock_qs
        mock_qs.order_by.return_value = []
        task.sections.filter.return_value = mock_qs
        result = SolutionGenerator._get_existing_sections(task)
        assert isinstance(result, dict)

