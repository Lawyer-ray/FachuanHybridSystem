"""Tests for FilenameTemplateService."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.filename_template_service import (
    FilenameTemplateService,
    COURT_DOC_DEFAULT,
    GENERATED_DOC_DEFAULT,
)


# ---------------------------------------------------------------------------
# _render
# ---------------------------------------------------------------------------


class TestRender:
    def test_basic(self):
        result = FilenameTemplateService._render(
            "{title}（{case_name}）_{date}收",
            {"title", "case_name", "date"},
            title="判决书",
            case_name="张三",
            date="20250115",
        )
        assert result == "判决书（张三）_20250115收"

    def test_invalid_placeholder_warns(self):
        result = FilenameTemplateService._render(
            "{title} {unknown}",
            {"title"},
            title="判决书",
        )
        # Unknown placeholder is kept as-is
        assert "{unknown}" in result

    def test_no_placeholders(self):
        result = FilenameTemplateService._render("plain text", set())
        assert result == "plain text"


# ---------------------------------------------------------------------------
# get_unique_filepath
# ---------------------------------------------------------------------------


class TestGetUniqueFilePath:
    def test_no_conflict(self, tmp_path: Path):
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test.pdf"
        assert str(tmp_path) in filepath

    def test_with_conflict(self, tmp_path: Path):
        (tmp_path / "test.pdf").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test_1.pdf"

    def test_multiple_conflicts(self, tmp_path: Path):
        (tmp_path / "test.pdf").touch()
        (tmp_path / "test_1.pdf").touch()
        (tmp_path / "test_2.pdf").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test_3.pdf"

    def test_100_conflicts_fallback_to_timestamp(self, tmp_path: Path):
        for i in range(1, 101):
            (tmp_path / f"test_{i}.pdf").touch()
        (tmp_path / "test.pdf").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        # Should use timestamp fallback after counter hits 100
        assert name.startswith("test_")
        assert name.endswith(".pdf")


# ---------------------------------------------------------------------------
# render_court_doc
# ---------------------------------------------------------------------------


class TestRenderCourtDoc:
    def test_default_template(self):
        with patch.object(FilenameTemplateService, "_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            result = FilenameTemplateService.render_court_doc(
                title="判决书", case_name="张三", date="20250115"
            )
            assert result == "判决书（张三）_20250115收"


# ---------------------------------------------------------------------------
# render_generated_doc
# ---------------------------------------------------------------------------


class TestRenderGeneratedDoc:
    def test_default_template(self):
        with patch.object(FilenameTemplateService, "_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            result = FilenameTemplateService.render_generated_doc(
                doc_type="起诉状", case_name="张三", version="1", date="20250115"
            )
            assert "起诉状" in result
            assert "张三" in result


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_found(self):
        with patch.object(FilenameTemplateService, "_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value="custom"))
            result = FilenameTemplateService.get_template("key", "default")
            assert result == "custom"

    def test_not_found(self):
        with patch.object(FilenameTemplateService, "_config_service") as mock_svc:
            mock_svc.return_value = MagicMock(get_value=MagicMock(return_value=""))
            result = FilenameTemplateService.get_template("key", "default")
            assert result == "default"
