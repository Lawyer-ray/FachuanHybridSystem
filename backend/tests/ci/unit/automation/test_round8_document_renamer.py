"""Tests for document_renamer (DocumentRenamer helper methods)."""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.document_renamer import DocumentRenamer


@pytest.fixture()
def renamer() -> DocumentRenamer:
    with patch("apps.automation.services.sms.document_renamer.get_config", return_value="50"):
        return DocumentRenamer()


# ---------------------------------------------------------------------------
# _sanitize_filename_part
# ---------------------------------------------------------------------------


class TestSanitizeFilenamePart:
    def test_empty(self, renamer: DocumentRenamer):
        assert renamer._sanitize_filename_part("") == ""

    def test_none(self, renamer: DocumentRenamer):
        assert renamer._sanitize_filename_part("") == ""

    def test_illegal_chars(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part('test<>:"|?*\\/')
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result

    def test_english_parens(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part("test(abc)")
        assert "(" not in result
        assert ")" not in result

    def test_chinese_parens_preserved(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part("test（abc）")
        assert "（" in result
        assert "）" in result

    def test_control_chars(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part("test\x00\x01value")
        assert "\x00" not in result

    def test_strips_dots_and_spaces(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part("  test  ")
        assert result == "test"

    def test_leading_dots(self, renamer: DocumentRenamer):
        result = renamer._sanitize_filename_part(".test.")
        assert result == "test"


# ---------------------------------------------------------------------------
# _normalize_title_candidate
# ---------------------------------------------------------------------------


class TestNormalizeTitleCandidate:
    def test_empty(self, renamer: DocumentRenamer):
        assert renamer._normalize_title_candidate("") == ""

    def test_none(self, renamer: DocumentRenamer):
        assert renamer._normalize_title_candidate("") == ""

    def test_removes_quotes(self, renamer: DocumentRenamer):
        result = renamer._normalize_title_candidate('"判决书"')
        assert result == "判决书"

    def test_removes_prefix(self, renamer: DocumentRenamer):
        result = renamer._normalize_title_candidate("某某法院_判决书")
        assert "某某法院_" not in result

    def test_removes_pdf_suffix(self, renamer: DocumentRenamer):
        result = renamer._normalize_title_candidate("判决书.pdf")
        assert result == "判决书"

    def test_removes_court_prefix(self, renamer: DocumentRenamer):
        result = renamer._normalize_title_candidate("佛山市禅城区人民法院民事判决书")
        assert "人民法院" not in result
        assert "判决书" in result


# ---------------------------------------------------------------------------
# _match_title_from_text
# ---------------------------------------------------------------------------


class TestMatchTitleFromText:
    def test_known_title(self, renamer: DocumentRenamer):
        result = renamer._match_title_from_text("广东省佛山市禅城区人民法院民事判决书")
        assert result == "民事判决书"

    def test_longest_match_preferred(self, renamer: DocumentRenamer):
        # "裁判文书生效证明" should be preferred over "调解书"
        result = renamer._match_title_from_text("裁判文书生效证明")
        assert result == "裁判文书生效证明"

    def test_no_match(self, renamer: DocumentRenamer):
        result = renamer._match_title_from_text("随机文本无匹配")
        assert result is None

    def test_empty(self, renamer: DocumentRenamer):
        assert renamer._match_title_from_text("") is None


# ---------------------------------------------------------------------------
# _extract_title_from_filename
# ---------------------------------------------------------------------------


class TestExtractTitleFromFilename:
    def test_known_title_in_filename(self, renamer: DocumentRenamer):
        result = renamer._extract_title_from_filename("/path/民事判决书.pdf")
        assert result == "民事判决书"

    def test_fallback_to_filename(self, renamer: DocumentRenamer):
        result = renamer._extract_title_from_filename("/path/random_doc.pdf")
        assert result == "random_doc"


# ---------------------------------------------------------------------------
# generate_filename
# ---------------------------------------------------------------------------


class TestGenerateFilename:
    def test_basic(self, renamer: DocumentRenamer):
        with patch("apps.automation.services.sms.document_renamer.FilenameTemplateService") as mock_tpl:
            mock_tpl.render_court_doc.return_value = "判决书（张三诉李四）_20250115收"
            result = renamer.generate_filename("判决书", "张三诉李四", date(2025, 1, 15))
            assert result == "判决书（张三诉李四）_20250115收.pdf"

    def test_empty_title(self, renamer: DocumentRenamer):
        with patch("apps.automation.services.sms.document_renamer.FilenameTemplateService") as mock_tpl:
            mock_tpl.render_court_doc.return_value = "司法文书（张三诉李四）_20250115收"
            result = renamer.generate_filename("", "张三诉李四", date(2025, 1, 15))
            assert "司法文书" in result

    def test_empty_case_name(self, renamer: DocumentRenamer):
        with patch("apps.automation.services.sms.document_renamer.FilenameTemplateService") as mock_tpl:
            mock_tpl.render_court_doc.return_value = "判决书（未知案件）_20250115收"
            result = renamer.generate_filename("判决书", "", date(2025, 1, 15))
            assert "未知案件" in result


# ---------------------------------------------------------------------------
# _get_title_extraction_limit
# ---------------------------------------------------------------------------


class TestGetTitleExtractionLimit:
    def test_default(self):
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value=""):
            renamer = DocumentRenamer()
            assert renamer.title_extraction_limit == DocumentRenamer.DEFAULT_TITLE_EXTRACTION_LIMIT

    def test_valid_value(self):
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value="100"):
            renamer = DocumentRenamer()
            assert renamer.title_extraction_limit == 100

    def test_invalid_value(self):
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value="abc"):
            renamer = DocumentRenamer()
            assert renamer.title_extraction_limit == DocumentRenamer.DEFAULT_TITLE_EXTRACTION_LIMIT

    def test_below_minimum(self):
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value="5"):
            renamer = DocumentRenamer()
            assert renamer.title_extraction_limit == 20

    def test_above_maximum(self):
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value="99999"):
            renamer = DocumentRenamer()
            assert renamer.title_extraction_limit == 5000
