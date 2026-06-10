"""Tests for refactored pure functions from core/services/filename_template_service.py."""

from __future__ import annotations

import pytest

from apps.core.services.filename_template_service import (
    FilenameTemplateService,
    COURT_DOC_KEY,
    COURT_DOC_DEFAULT,
    COURT_DOC_PLACEHOLDERS,
    GENERATED_DOC_KEY,
    GENERATED_DOC_DEFAULT,
    GENERATED_DOC_PLACEHOLDERS,
)


class TestConstants:
    """Tests for module-level constants."""

    def test_court_doc_key(self):
        assert COURT_DOC_KEY == "FILENAME_TEMPLATE_COURT_DOC"

    def test_court_doc_default(self):
        assert "{title}" in COURT_DOC_DEFAULT
        assert "{case_name}" in COURT_DOC_DEFAULT
        assert "{date}" in COURT_DOC_DEFAULT

    def test_court_doc_placeholders(self):
        assert "title" in COURT_DOC_PLACEHOLDERS
        assert "case_name" in COURT_DOC_PLACEHOLDERS
        assert "date" in COURT_DOC_PLACEHOLDERS

    def test_generated_doc_key(self):
        assert GENERATED_DOC_KEY == "FILENAME_TEMPLATE_GENERATED_DOC"

    def test_generated_doc_default(self):
        assert "{doc_type}" in GENERATED_DOC_DEFAULT
        assert "{case_name}" in GENERATED_DOC_DEFAULT
        assert "{version}" in GENERATED_DOC_DEFAULT
        assert "{date}" in GENERATED_DOC_DEFAULT

    def test_generated_doc_placeholders(self):
        assert "doc_type" in GENERATED_DOC_PLACEHOLDERS
        assert "case_name" in GENERATED_DOC_PLACEHOLDERS
        assert "version" in GENERATED_DOC_PLACEHOLDERS
        assert "date" in GENERATED_DOC_PLACEHOLDERS


class TestRender:
    """Tests for _render static method."""

    def test_basic_render(self):
        result = FilenameTemplateService._render(
            "{title} - {date}",
            {"title", "date"},
            title="Test",
            date="20260115",
        )
        assert result == "Test - 20260115"

    def test_multiple_placeholders(self):
        result = FilenameTemplateService._render(
            "{doc_type}({case_name})V{version}_{date}",
            {"doc_type", "case_name", "version", "date"},
            doc_type="起诉状",
            case_name="XX案",
            version="1",
            date="20260115",
        )
        assert result == "起诉状(XX案)V1_20260115"

    def test_missing_placeholder_preserved(self):
        result = FilenameTemplateService._render(
            "{title} - {missing}",
            {"title"},
            title="Test",
        )
        assert result == "Test - {missing}"

    def test_empty_template(self):
        result = FilenameTemplateService._render("", set())
        assert result == ""

    def test_no_placeholders(self):
        result = FilenameTemplateService._render("plain text", set())
        assert result == "plain text"


class TestGetUniqueFilepath:
    """Tests for get_unique_filepath static method."""

    def test_no_conflict(self, tmp_path):
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "test.txt")
        assert filename == "test.txt"
        assert filepath == str(tmp_path / "test.txt")

    def test_single_conflict(self, tmp_path):
        (tmp_path / "test.txt").touch()
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "test.txt")
        assert filename == "test_1.txt"
        assert filepath == str(tmp_path / "test_1.txt")

    def test_multiple_conflicts(self, tmp_path):
        (tmp_path / "test.txt").touch()
        (tmp_path / "test_1.txt").touch()
        (tmp_path / "test_2.txt").touch()
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "test.txt")
        assert filename == "test_3.txt"

    def test_no_extension(self, tmp_path):
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "test")
        assert filename == "test"

    def test_complex_extension(self, tmp_path):
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "archive.tar.gz")
        assert filename == "archive.tar.gz"

    def test_chinese_filename(self, tmp_path):
        filepath, filename = FilenameTemplateService.get_unique_filepath(str(tmp_path), "证据清单一.docx")
        assert filename == "证据清单一.docx"
