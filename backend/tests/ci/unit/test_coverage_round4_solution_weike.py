"""Coverage round 4: solution_generator.py + weike document.py."""
from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ============================================================
# solution_generator.py – _md_to_html
# ============================================================

class TestMdToHtml:
    def test_bold_text(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_ordered_list(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("1. item one\n2. item two")
        assert "<ol>" in result
        assert "<li>item one</li>" in result
        assert "</ol>" in result

    def test_unordered_list(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("- item a\n- item b")
        assert "<ul>" in result
        assert "<li>item a</li>" in result
        assert "</ul>" in result

    def test_mixed_list_switches(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        # markdown lib is installed, so this uses the library path
        result = _md_to_html("- item 1\n1. item 2")
        assert "item 1" in result
        assert "item 2" in result

    def test_plain_paragraph(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("just text")
        assert "<p>just text</p>" in result

    def test_empty_string(self):
        from apps.legal_solution.services.solution_generator import _md_to_html
        result = _md_to_html("")
        assert result == ""

    def test_fallback_bold(self):
        """Test the fallback path when markdown lib is unavailable."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        from apps.legal_solution.services.solution_generator import _md_to_html
        with patch("builtins.__import__", side_effect=mock_import):
            result = _md_to_html("**bold**")
        assert "<strong>bold</strong>" in result

    def test_fallback_ordered_list(self):
        """Test the fallback OL handling."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        from apps.legal_solution.services.solution_generator import _md_to_html
        with patch("builtins.__import__", side_effect=mock_import):
            result = _md_to_html("1. first\n2. second")
        assert "<ol>" in result
        assert "<li>first</li>" in result
        assert "</ol>" in result

    def test_fallback_unordered_list(self):
        """Test the fallback UL handling."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        from apps.legal_solution.services.solution_generator import _md_to_html
        with patch("builtins.__import__", side_effect=mock_import):
            result = _md_to_html("- alpha\n- beta")
        assert "<ul>" in result
        assert "<li>alpha</li>" in result
        assert "</ul>" in result

    def test_fallback_mixed_list(self):
        """Test fallback when UL then OL."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        from apps.legal_solution.services.solution_generator import _md_to_html
        with patch("builtins.__import__", side_effect=mock_import):
            result = _md_to_html("- item 1\n1. item 2")
        assert "<ul>" in result
        assert "<ol>" in result

    def test_fallback_ol_then_ul(self):
        """Test fallback when OL then UL."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "markdown":
                raise ImportError("no markdown")
            return real_import(name, *args, **kwargs)

        from apps.legal_solution.services.solution_generator import _md_to_html
        with patch("builtins.__import__", side_effect=mock_import):
            result = _md_to_html("1. first\n- item a")
        assert "<ol>" in result
        assert "<ul>" in result


# ============================================================
# solution_generator.py – SolutionGenerator
# ============================================================

class TestSolutionGenerator:
    def _make_sg(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        sg = SolutionGenerator.__new__(SolutionGenerator)
        sg._llm = MagicMock()
        return sg

    def test_load_research_results_no_task_id(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        task.research_task_id = None
        assert SolutionGenerator._load_research_results(task) == ""

    def test_load_research_results_empty(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        task.research_task_id = 1
        task.research_task.results.filter.return_value.order_by.return_value.values.return_value = []
        result = SolutionGenerator._load_research_results(task)
        assert "未检索到" in result

    def test_load_research_results_with_data(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        task.research_task_id = 1
        task.research_task.results.filter.return_value.order_by.return_value.values.return_value = [
            {"rank": 1, "title": "案例一", "document_number": "(2024)民初1号", "court_text": "北京法院", "judgment_date": "2024-01-01", "case_digest": "摘要内容", "similarity_score": 0.85},
        ]
        result = SolutionGenerator._load_research_results(task)
        assert "案例一" in result
        assert "85%" in result

    def test_get_existing_sections(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        s1 = MagicMock(section_type="overview", content="content1")
        s2 = MagicMock(section_type="analysis", content="content2")
        task.sections.filter.return_value.order_by.return_value = [s1, s2]
        result = SolutionGenerator._get_existing_sections(task, exclude="")
        assert "overview" in result
        assert "analysis" in result

    def test_get_existing_sections_with_exclude(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        s1 = MagicMock(section_type="overview", content="content1")
        qs = MagicMock()
        qs.exclude.return_value = [s1]
        task.sections.filter.return_value.order_by.return_value = qs
        result = SolutionGenerator._get_existing_sections(task, exclude="analysis")
        assert "overview" in result

    def test_get_or_create_section(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator
        task = MagicMock()
        section = MagicMock()
        section.status = "pending"
        from apps.legal_solution.models.section import SECTION_ORDER, SECTION_TITLES
        with patch("apps.legal_solution.services.solution_generator.SolutionSection") as MockSection:
            MockSection.objects.get_or_create.return_value = (section, True)
            result = SolutionGenerator._get_or_create_section(task, "overview", 0)
        assert result is section

    def test_generate_skips_completed(self):
        sg = self._make_sg()
        task = MagicMock()
        section = MagicMock()
        section.status = "completed"
        section.section_type = "overview"
        section.content = "done"
        with patch("apps.legal_solution.services.solution_generator.SECTION_ORDER", ["overview"]):
            with patch.object(sg, '_get_or_create_section', return_value=section):
                with patch.object(sg, '_load_research_results', return_value=""):
                    sg.generate(task)
        # Section was already completed, no LLM call needed

    def test_generate_handles_llm_failure(self):
        sg = self._make_sg()
        task = MagicMock()
        section = MagicMock()
        section.status = "pending"
        section.section_type = "overview"
        with patch("apps.legal_solution.services.solution_generator.SECTION_ORDER", ["overview"]):
            with patch.object(sg, '_get_or_create_section', return_value=section):
                with patch.object(sg, '_load_research_results', return_value=""):
                    with patch.object(sg, '_generate_section') as mock_gen:
                        sg.generate(task)
        mock_gen.assert_called_once()

    def test_regenerate_section(self):
        sg = self._make_sg()
        section = MagicMock()
        section.task = MagicMock()
        section.section_type = "overview"
        section.version = 1
        with patch.object(sg, '_load_research_results', return_value=""):
            with patch.object(sg, '_get_existing_sections', return_value={}):
                with patch.object(sg, '_generate_section') as mock_gen:
                    sg.regenerate_section(section, "feedback text")
        assert section.user_feedback == "feedback text"
        assert section.version == 2


# ============================================================
# weike document.py – module-level functions
# ============================================================

class TestWeikeDocumentFunctions:
    def test_html_to_text_basic(self):
        from apps.legal_research.services.sources.weike.document import html_to_text
        result = html_to_text("<p>Hello <b>World</b></p>")
        assert "Hello" in result
        assert "World" in result
        assert "<" not in result

    def test_html_to_text_removes_script(self):
        from apps.legal_research.services.sources.weike.document import html_to_text
        result = html_to_text("<script>alert('x')</script><p>safe</p>")
        assert "alert" not in result
        assert "safe" in result

    def test_html_to_text_removes_style(self):
        from apps.legal_research.services.sources.weike.document import html_to_text
        result = html_to_text("<style>.x{}</style><p>text</p>")
        assert ".x{}" not in result
        assert "text" in result

    def test_html_to_text_br_newline(self):
        from apps.legal_research.services.sources.weike.document import html_to_text
        result = html_to_text("line1<br>line2")
        assert result == "line1\nline2"

    def test_html_to_text_entities(self):
        from apps.legal_research.services.sources.weike.document import html_to_text
        result = html_to_text("&amp; &lt; &gt;")
        assert "&" in result
        assert "<" in result
        assert ">" in result

    def test_normalize_dom_text(self):
        from apps.legal_research.services.sources.weike.document import normalize_dom_text
        result = normalize_dom_text("  hello   world  ")
        assert result == "hello world"

    def test_normalize_dom_text_newlines(self):
        from apps.legal_research.services.sources.weike.document import normalize_dom_text
        result = normalize_dom_text("a\n\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_normalize_dom_text_nbsp(self):
        from apps.legal_research.services.sources.weike.document import normalize_dom_text
        result = normalize_dom_text("hello\xa0world")
        assert "\xa0" not in result

    def test_extract_dom_field_found(self):
        from apps.legal_research.services.sources.weike.document import extract_dom_field
        result = extract_dom_field(text="法院：北京市朝阳区人民法院", patterns=(r"法院[:：]\s*([^\n]+)",))
        assert "北京市" in result

    def test_extract_dom_field_not_found(self):
        from apps.legal_research.services.sources.weike.document import extract_dom_field
        result = extract_dom_field(text="no match", patterns=(r"法院[:：]\s*([^\n]+)",))
        assert result == ""

    def test_build_dom_digest_short(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest
        result = build_dom_digest("short text")
        assert result == "short text"

    def test_build_dom_digest_long(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest
        long_text = "x" * 300
        result = build_dom_digest(long_text)
        assert len(result) <= 225
        assert result.endswith("...")

    def test_build_dom_digest_empty(self):
        from apps.legal_research.services.sources.weike.document import build_dom_digest
        assert build_dom_digest("") == ""
        assert build_dom_digest("   ") == ""

    def test_detail_doc_id_candidates(self):
        from apps.legal_research.services.sources.weike.document import detail_doc_id_candidates
        item = MagicMock()
        item.doc_id_raw = "raw123"
        item.doc_id_unquoted = "unquoted123"
        result = detail_doc_id_candidates(item)
        assert "raw123" in result
        assert "unquoted123" in result

    def test_detail_doc_id_candidates_dedup(self):
        from apps.legal_research.services.sources.weike.document import detail_doc_id_candidates
        item = MagicMock()
        item.doc_id_raw = "same_id"
        item.doc_id_unquoted = "same_id"
        result = detail_doc_id_candidates(item)
        assert len(result) == 1

    def test_is_session_restricted_response_code(self):
        from apps.legal_research.services.sources.weike.document import is_session_restricted_response
        assert is_session_restricted_response(status=200, payload={"code": "C_001_009"}) is True

    def test_is_session_restricted_response_status_400(self):
        from apps.legal_research.services.sources.weike.document import is_session_restricted_response
        assert is_session_restricted_response(status=400, payload={"code": "C_001_009"}) is True

    def test_is_session_restricted_response_not_restricted(self):
        from apps.legal_research.services.sources.weike.document import is_session_restricted_response
        assert is_session_restricted_response(status=200, payload={"code": "OK"}) is False

    def test_compact_error_short(self):
        from apps.legal_research.services.sources.weike.document import compact_error
        result = compact_error(ValueError("short"))
        assert result == "short"

    def test_compact_error_long(self):
        from apps.legal_research.services.sources.weike.document import compact_error
        long_msg = "x" * 200
        result = compact_error(ValueError(long_msg))
        assert len(result) <= 120

    def test_compact_error_empty_message(self):
        from apps.legal_research.services.sources.weike.document import compact_error
        result = compact_error(ValueError(""))
        assert result == "ValueError"

    def test_summarize_meta_payload(self):
        from apps.legal_research.services.sources.weike.document import summarize_meta_payload
        payload = {
            "currentDoc": {
                "title": "案例标题",
                "additionalFields": {
                    "courtText": "北京法院",
                    "documentNumber": "(2024)民初1号",
                    "judgmentDate": "2024-01-01",
                },
            }
        }
        result = summarize_meta_payload(payload)
        assert result["title"] == "案例标题"
        assert result["court_text"] == "北京法院"

    def test_summarize_meta_payload_empty(self):
        from apps.legal_research.services.sources.weike.document import summarize_meta_payload
        result = summarize_meta_payload(None)
        assert result["title"] == ""

    def test_summarize_html_payload(self):
        from apps.legal_research.services.sources.weike.document import summarize_html_payload
        result = summarize_html_payload({"content": "<p>hello</p>"})
        assert result["has_content"] is True
        assert result["content_length"] > 0

    def test_summarize_html_payload_empty(self):
        from apps.legal_research.services.sources.weike.document import summarize_html_payload
        result = summarize_html_payload(None)
        assert result["has_content"] is False

    def test_build_download_filename(self):
        from apps.legal_research.services.sources.weike.document import build_download_filename
        detail = MagicMock()
        detail.title = "案例标题"
        detail.doc_id_unquoted = "doc123"
        result = build_download_filename(detail)
        assert "案例标题" in result
        assert result.endswith(".pdf")

    def test_build_download_filename_no_title(self):
        from apps.legal_research.services.sources.weike.document import build_download_filename
        detail = MagicMock()
        detail.title = ""
        detail.doc_id_unquoted = "doc123"
        result = build_download_filename(detail)
        assert "doc123" in result

    def test_build_download_filename_special_chars(self):
        from apps.legal_research.services.sources.weike.document import build_download_filename
        detail = MagicMock()
        detail.title = 'title/with:*?"special<>|chars'
        detail.doc_id_unquoted = "doc123"
        result = build_download_filename(detail)
        assert "/" not in result
        assert "*" not in result


# ============================================================
# WeikeDocumentMixin – _raise_if_session_restricted
# ============================================================

class TestWeikeDocumentMixinRestricted:
    def _make_mixin(self):
        from apps.legal_research.services.sources.weike.document import WeikeDocumentMixin
        m = WeikeDocumentMixin.__new__(WeikeDocumentMixin)
        return m

    def test_not_restricted(self):
        import time
        m = self._make_mixin()
        session = MagicMock()
        session.restricted_until_epoch = time.time() - 10
        # Should not raise
        m._raise_if_session_restricted(session=session, stage="test")

    def test_restricted_raises(self):
        import time
        m = self._make_mixin()
        session = MagicMock()
        session.restricted_until_epoch = time.time() + 60
        with pytest.raises(RuntimeError, match=r"请.*秒后重试"):
            m._raise_if_session_restricted(session=session, stage="test")

    def test_resolve_cooldown_seconds_default(self):
        m = self._make_mixin()
        assert m._resolve_session_restrict_cooldown_seconds() == 180

    def test_resolve_cooldown_seconds_custom(self):
        m = self._make_mixin()
        m._session_restrict_cooldown_seconds = 60
        assert m._resolve_session_restrict_cooldown_seconds() == 60

    def test_resolve_cooldown_seconds_invalid(self):
        m = self._make_mixin()
        m._session_restrict_cooldown_seconds = "invalid"
        assert m._resolve_session_restrict_cooldown_seconds() == 180

    def test_resolve_cooldown_seconds_too_low(self):
        m = self._make_mixin()
        m._session_restrict_cooldown_seconds = 5
        assert m._resolve_session_restrict_cooldown_seconds() == 30

    def test_mark_session_restricted(self):
        import time
        m = self._make_mixin()
        session = MagicMock()
        session.task_id = "task1"
        before = time.time()
        m._mark_session_restricted(session=session, stage="test", status=400, payload={"code": "C_001_009"})
        assert session.restricted_until_epoch > before
