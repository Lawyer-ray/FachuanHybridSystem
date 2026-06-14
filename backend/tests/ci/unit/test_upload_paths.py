"""Tests for apps.core.filesystem.upload_paths."""

from __future__ import annotations

from unittest.mock import patch
from datetime import datetime

import pytest

from apps.core.filesystem.upload_paths import (
    DatedOriginalPath,
    DatedUUIDPath,
    EntityIdPath,
    EntitySubPath,
    _sanitize,
)


class TestSanitize:
    def test_normal_filename(self):
        assert _sanitize("document.pdf") == "document.pdf"

    def test_with_path(self):
        assert _sanitize("/path/to/file.txt") == "file.txt"

    def test_backslash_path(self):
        assert _sanitize("C:\\Users\\file.doc") == "file.doc"

    def test_dangerous_chars(self):
        result = _sanitize("file name@#$.pdf")
        assert "@" not in result
        assert "#" not in result

    def test_chinese_chars_preserved(self):
        result = _sanitize("文件名.pdf")
        assert "文件名" in result
        assert ".pdf" in result

    def test_empty_returns_file(self):
        assert _sanitize("") == "file"

    def test_only_underscores(self):
        result = _sanitize("___")
        assert result == "file" or len(result) > 0


class TestDatedUUIDPath:
    @patch("apps.core.filesystem.upload_paths.uuid")
    @patch("apps.core.filesystem.upload_paths.datetime")
    def test_call(self, mock_dt, mock_uuid):
        mock_dt.now.return_value = datetime(2024, 6, 15)
        mock_uuid.uuid4.return_value.hex = "abc123def456"
        path_fn = DatedUUIDPath("my_entity")
        result = path_fn(None, "test.pdf")
        assert result == "my_entity/2024/06/abc123def456.pdf"

    def test_deconstruct(self):
        path_fn = DatedUUIDPath("entity")
        name, args, kwargs = path_fn.deconstruct()
        assert "DatedUUIDPath" in name
        assert args == ("entity",)
        assert kwargs == {}


class TestDatedOriginalPath:
    @patch("apps.core.filesystem.upload_paths.datetime")
    def test_call(self, mock_dt):
        mock_dt.now.return_value = datetime(2024, 3, 1)
        path_fn = DatedOriginalPath("docs")
        result = path_fn(None, "report.pdf")
        assert result == "docs/2024/03/report.pdf"

    def test_deconstruct(self):
        path_fn = DatedOriginalPath("docs")
        name, args, kwargs = path_fn.deconstruct()
        assert "DatedOriginalPath" in name
        assert args == ("docs",)


class TestEntityIdPath:
    def test_with_pk(self):
        instance = type("Obj", (), {"pk": 42})()
        path_fn = EntityIdPath("cases")
        result = path_fn(instance, "doc.pdf")
        assert result == "cases/42/doc.pdf"

    def test_without_pk(self):
        path_fn = EntityIdPath("cases")
        result = path_fn(None, "doc.pdf")
        assert result == "cases/unsaved/doc.pdf"

    def test_custom_id_attr(self):
        instance = type("Obj", (), {"my_id": 99})()
        path_fn = EntityIdPath("cases", id_attr="my_id")
        result = path_fn(instance, "doc.pdf")
        assert result == "cases/99/doc.pdf"

    def test_deconstruct(self):
        path_fn = EntityIdPath("cases", id_attr="pk")
        name, args, kwargs = path_fn.deconstruct()
        assert args == ("cases", "pk")


class TestEntitySubPath:
    def test_call(self):
        path_fn = EntitySubPath("exports", "2024")
        result = path_fn(None, "any.pdf")
        assert result == "exports/2024/"

    def test_deconstruct(self):
        path_fn = EntitySubPath("exports", "2024")
        name, args, kwargs = path_fn.deconstruct()
        assert args == ("exports", "2024")
