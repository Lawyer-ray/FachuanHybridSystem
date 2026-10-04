"""SolutionGenerator 单元测试。

覆盖 markdown→HTML 的回退转换器与消毒、generate 的段落编排/进度推进/
LLM 模型回写/失败重试、regenerate_section 的反馈重生成、
_load_research_results 与 _get_existing_sections。LLM 一律 mock。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_solution.models import SectionStatus, SolutionSection, SolutionTask
from apps.legal_solution.services.solution_generator import SolutionGenerator, _fallback_md_to_html, _md_to_html

GEN_MODULE = "apps.legal_solution.services.solution_generator"


@pytest.fixture
def solution_task(db: None) -> SolutionTask:
    from apps.organization.models import AccountCredential, Lawyer

    lawyer = Lawyer.objects.create_user(username="gen-lawyer", email="gen@example.com")
    credential = AccountCredential.objects.create(lawyer=lawyer, site_name="wkxx", account="acct", password="pwd")
    return SolutionTask.objects.create(
        case_summary="测试案情简述",
        keyword="测试",
        credential=credential,
    )


def _llm_response(content: str, model: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.model = model
    return resp


def _generator(chat_return=None, *, chat_side_effect=None) -> SolutionGenerator:
    mock_llm = MagicMock()
    if chat_side_effect is not None:
        mock_llm.chat.side_effect = chat_side_effect
    else:
        mock_llm.chat.return_value = chat_return
    with patch(f"{GEN_MODULE}.ServiceLocator.get_llm_service", return_value=mock_llm):
        gen = SolutionGenerator()
    return gen


class TestFallbackMdToHtml:
    def test_bold_and_paragraph(self) -> None:
        html = _fallback_md_to_html("**重点**段落")
        assert "<strong>重点</strong>" in html
        assert "<p>" in html

    def test_ordered_list_variants(self) -> None:
        html = _fallback_md_to_html("1. 甲\n2. 乙\n二、丙".replace("二、", "2、"))
        assert "<ol>" in html and "<li>甲</li>" in html and "</ol>" in html

    def test_unordered_list_variants(self) -> None:
        html = _fallback_md_to_html("- 甲\n* 乙\n• 丙")
        assert "<ul>" in html and "<li>乙</li>" in html and "</ul>" in html

    def test_list_transition_closes_previous(self) -> None:
        html = _fallback_md_to_html("- 项\n1. 序")
        assert "<ul>" in html and "</ul>" in html
        assert "<ol>" in html and "</ol>" in html

    def test_blank_lines_skipped(self) -> None:
        html = _fallback_md_to_html("段落\n\n   \n尾段")
        assert "<p>段落</p>" in html
        assert "<p>   </p>" not in html
        assert "<p>尾段</p>" in html

    def test_raw_html_escaped(self) -> None:
        html = _fallback_md_to_html("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestMdToHtml:
    def test_output_is_sanitized(self) -> None:
        html = _md_to_html("正常 **加粗**\n\n<script>alert(1)</script>")
        assert "<strong>加粗</strong>" in html
        assert "<script>" not in html

    def test_fallback_branch_on_import_error(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _no_markdown(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        with patch(f"{GEN_MODULE}.sanitize_report_html", side_effect=lambda s: s):
            with patch("builtins.__import__", side_effect=_no_markdown):
                html = _md_to_html("**手写回退**")
        assert "<strong>手写回退</strong>" in html


@pytest.mark.django_db
class TestGenerate:
    def test_generates_all_sections_and_progress(self, solution_task) -> None:
        from apps.legal_solution.models.section import SECTION_ORDER

        gen = _generator(chat_return=_llm_response("生成内容 **加粗**", model="glm-test"))
        gen.generate(solution_task)

        solution_task.refresh_from_db()
        assert solution_task.progress == 100
        assert "7/7" in solution_task.message
        sections = list(SolutionSection.objects.filter(task=solution_task).order_by("order"))
        assert [s.section_type for s in sections] == list(SECTION_ORDER)
        assert all(s.status == SectionStatus.COMPLETED for s in sections)
        assert all("<strong>加粗</strong>" in s.html_content for s in sections)
        # LLM 模型回写（task.llm_model 原为空）
        assert solution_task.llm_model == "glm-test"

    def test_existing_llm_model_not_overwritten(self, solution_task) -> None:
        solution_task.llm_model = "pinned-model"
        solution_task.save(update_fields=["llm_model"])

        gen = _generator(chat_return=_llm_response("内容", model="other-model"))
        gen.generate(solution_task)

        solution_task.refresh_from_db()
        assert solution_task.llm_model == "pinned-model"

    def test_completed_sections_reused_without_llm_call(self, solution_task) -> None:
        SolutionSection.objects.create(
            task=solution_task,
            section_type="case_analysis",
            order=0,
            title="案情分析",
            status=SectionStatus.COMPLETED,
            content="既有内容",
        )
        gen = _generator(chat_return=_llm_response("新内容"))
        gen.generate(solution_task)

        reused = SolutionSection.objects.get(task=solution_task, section_type="case_analysis")
        assert reused.content == "既有内容"

    def test_llm_failure_marks_section_failed(self, solution_task) -> None:
        gen = _generator(chat_side_effect=RuntimeError("llm down"))
        with patch(f"{GEN_MODULE}.time.sleep") as mock_sleep:
            gen.generate(solution_task)

        sections = list(SolutionSection.objects.filter(task=solution_task))
        assert sections, "段落仍应被创建"
        assert all(s.status == SectionStatus.FAILED for s in sections)
        # _RETRY=2：每段两次尝试之间 sleep 一次
        assert mock_sleep.call_count >= len(sections)

    def test_empty_llm_content_treated_as_failure(self, solution_task) -> None:
        gen = _generator(chat_return=_llm_response("   "))
        with patch(f"{GEN_MODULE}.time.sleep"):
            gen.generate(solution_task)

        sections = list(SolutionSection.objects.filter(task=solution_task))
        assert all(s.status == SectionStatus.FAILED for s in sections)


@pytest.mark.django_db
class TestRegenerateSection:
    def test_regenerate_increments_version_and_saves_feedback(self, solution_task) -> None:
        section = SolutionSection.objects.create(
            task=solution_task,
            section_type="case_analysis",
            order=0,
            title="案情分析",
            status=SectionStatus.COMPLETED,
            content="初版",
        )
        gen = _generator(chat_return=_llm_response("重写后的内容"))
        gen.regenerate_section(section, feedback="更正式一些")

        section.refresh_from_db()
        assert section.status == SectionStatus.COMPLETED
        assert section.content == "重写后的内容"
        assert section.version == 2
        assert section.user_feedback == "更正式一些"


class TestLoadResearchResults:
    @staticmethod
    def _task_with_rows(rows: list[dict]) -> SimpleNamespace:
        """构造 research_task 替身：results.filter().order_by().values(...) → rows。"""
        values = MagicMock(return_value=rows)
        order_by = MagicMock(return_value=SimpleNamespace(values=values))
        results = SimpleNamespace(filter=MagicMock(return_value=SimpleNamespace(order_by=order_by)))
        return SimpleNamespace(research_task_id=5, research_task=SimpleNamespace(results=results))

    def test_no_research_task_returns_empty(self) -> None:
        task = SimpleNamespace(research_task_id=None)
        assert SolutionGenerator._load_research_results(task) == ""

    def test_empty_results_returns_placeholder(self) -> None:
        task = self._task_with_rows([])
        assert SolutionGenerator._load_research_results(task) == "未检索到类案。"

    def test_results_formatted_with_truncated_digest(self) -> None:
        rows = [
            {
                "rank": 1,
                "title": "张三诉李四",
                "document_number": "(2026)京01民初1号",
                "court_text": "北京一中院",
                "judgment_date": "2026-01-01",
                "case_digest": "摘" * 500,
                "similarity_score": 0.92,
            }
        ]
        text = SolutionGenerator._load_research_results(self._task_with_rows(rows))
        assert "【案例1】张三诉李四" in text
        assert "(2026)京01民初1号" in text
        assert "92%" in text
        assert "摘" * 500 not in text  # 摘要截断到 300 字
        assert "摘" * 300 in text


@pytest.mark.django_db
class TestGetExistingSections:
    def test_returns_completed_only_with_exclude(self, solution_task) -> None:
        SolutionSection.objects.create(
            task=solution_task,
            section_type="case_analysis",
            order=0,
            title="A",
            status=SectionStatus.COMPLETED,
            content="甲",
        )
        SolutionSection.objects.create(
            task=solution_task,
            section_type="legal_relation",
            order=1,
            title="B",
            status=SectionStatus.COMPLETED,
            content="乙",
        )
        SolutionSection.objects.create(
            task=solution_task,
            section_type="dispute_focus",
            order=2,
            title="C",
            status=SectionStatus.FAILED,
            content="丙",
        )

        all_completed = SolutionGenerator._get_existing_sections(solution_task)
        assert all_completed == {"case_analysis": "甲", "legal_relation": "乙"}

        excluded = SolutionGenerator._get_existing_sections(solution_task, exclude="case_analysis")
        assert excluded == {"legal_relation": "乙"}
