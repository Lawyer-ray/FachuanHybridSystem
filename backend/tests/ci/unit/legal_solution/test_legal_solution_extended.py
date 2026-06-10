"""Extended tests for legal_solution services - prompts, task_service, pdf_exporter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.legal_solution.services.prompts import (
    SYSTEM_PROMPT,
    _SECTION_PROMPTS,
    build_section_prompt,
)


class TestPrompts:
    def test_system_prompt_exists(self):
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0

    def test_section_prompts_keys(self):
        expected_keys = {
            "case_analysis",
            "legal_relation",
            "dispute_focus",
            "similar_cases",
            "litigation_strategy",
            "risk_assessment",
            "cost_estimate",
        }
        assert set(_SECTION_PROMPTS.keys()) == expected_keys

    def test_build_section_prompt_case_analysis(self):
        messages = build_section_prompt(
            section_type="case_analysis",
            case_summary="买卖合同纠纷案件",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "买卖合同纠纷案件" in messages[1]["content"]

    def test_build_section_prompt_legal_relation(self):
        messages = build_section_prompt(
            section_type="legal_relation",
            case_summary="买卖合同纠纷",
            existing_sections={"case_analysis": "案情分析内容"},
        )
        assert len(messages) == 2
        assert "案情分析内容" in messages[1]["content"]

    def test_build_section_prompt_dispute_focus(self):
        messages = build_section_prompt(
            section_type="dispute_focus",
            case_summary="买卖合同纠纷",
            existing_sections={"legal_relation": "法律关系内容"},
        )
        assert len(messages) == 2

    def test_build_section_prompt_similar_cases(self):
        messages = build_section_prompt(
            section_type="similar_cases",
            case_summary="买卖合同纠纷",
            research_results="类案检索结果内容",
        )
        assert len(messages) == 2
        assert "类案检索结果内容" in messages[1]["content"]

    def test_build_section_prompt_litigation_strategy(self):
        messages = build_section_prompt(
            section_type="litigation_strategy",
            case_summary="买卖合同纠纷",
            existing_sections={
                "dispute_focus": "争议焦点",
                "similar_cases": "类案参考",
            },
        )
        assert len(messages) == 2

    def test_build_section_prompt_risk_assessment(self):
        messages = build_section_prompt(
            section_type="risk_assessment",
            case_summary="买卖合同纠纷",
            existing_sections={"litigation_strategy": "诉讼策略"},
        )
        assert len(messages) == 2

    def test_build_section_prompt_cost_estimate(self):
        messages = build_section_prompt(
            section_type="cost_estimate",
            case_summary="买卖合同纠纷",
            existing_sections={"risk_assessment": "风险评估"},
        )
        assert len(messages) == 2

    def test_build_section_prompt_with_feedback(self):
        messages = build_section_prompt(
            section_type="case_analysis",
            case_summary="买卖合同纠纷",
            feedback="请更详细分析违约责任",
        )
        assert "用户调整意见" in messages[1]["content"]

    def test_build_section_prompt_no_research_results(self):
        messages = build_section_prompt(
            section_type="similar_cases",
            case_summary="买卖合同纠纷",
            research_results="",
        )
        assert "暂无类案检索结果" in messages[1]["content"]

    def test_build_section_prompt_no_existing_sections(self):
        messages = build_section_prompt(
            section_type="legal_relation",
            case_summary="买卖合同纠纷",
        )
        assert "待生成" in messages[1]["content"]


class TestLegalSolutionModels:
    def test_import_models(self):
        from apps.legal_solution.models import SolutionTask

        assert SolutionTask is not None


class TestLegalSolutionWiring:
    def test_import_task_service(self):
        from apps.legal_solution.services.task_service import SolutionTaskService

        assert SolutionTaskService is not None

    def test_import_pdf_exporter(self):
        from apps.legal_solution.services.pdf_exporter import PdfExporter

        assert PdfExporter is not None

    def test_import_html_renderer(self):
        from apps.legal_solution.services.html_renderer import HtmlRenderer

        assert HtmlRenderer is not None

    def test_import_solution_generator(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        assert SolutionGenerator is not None
