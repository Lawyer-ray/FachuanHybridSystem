"""Comprehensive tests for cases/utils.py"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.cases.utils import (
    CASE_LOG_ALLOWED_EXTENSIONS,
    CASE_LOG_MAX_FILE_SIZE,
    _basename,
    fix_sqlite_orphan_contract_fk,
    get_file_extension_lower,
    normalize_case_number,
    validate_case_log_attachment,
)


class TestBasename:
    """_basename() tests."""

    def test_simple_filename(self) -> None:
        assert _basename("test.pdf") == "test.pdf"

    def test_unix_path(self) -> None:
        assert _basename("/tmp/dir/test.pdf") == "test.pdf"

    def test_windows_path(self) -> None:
        assert _basename("C:\\Users\\test\\file.doc") == "file.doc"

    def test_mixed_separators(self) -> None:
        assert _basename("C:\\Users/test\\file.doc") == "file.doc"

    def test_empty_string(self) -> None:
        assert _basename("") == ""

    def test_none_input(self) -> None:
        assert _basename(None) == ""  # type: ignore[arg-type]

    def test_only_path_separator(self) -> None:
        assert _basename("/") == ""

    def test_backslash_only(self) -> None:
        assert _basename("\\") == ""


class TestGetFileExtensionLower:
    """get_file_extension_lower() tests."""

    def test_pdf(self) -> None:
        assert get_file_extension_lower("test.pdf") == ".pdf"

    def test_uppercase_extension(self) -> None:
        assert get_file_extension_lower("file.PDF") == ".pdf"

    def test_mixed_case(self) -> None:
        assert get_file_extension_lower("file.DocX") == ".docx"

    def test_no_extension(self) -> None:
        assert get_file_extension_lower("noext") == ""

    def test_dotfile_only(self) -> None:
        assert get_file_extension_lower(".hidden") == ".hidden"

    def test_path_with_extension(self) -> None:
        assert get_file_extension_lower("/tmp/dir/file.xlsx") == ".xlsx"

    def test_dot_only(self) -> None:
        assert get_file_extension_lower(".") == ""

    def test_dotdot(self) -> None:
        assert get_file_extension_lower("..") == ""

    def test_empty(self) -> None:
        assert get_file_extension_lower("") == ""

    def test_whitespace_name(self) -> None:
        assert get_file_extension_lower("  ") == ""

    def test_multiple_dots(self) -> None:
        assert get_file_extension_lower("file.backup.pdf") == ".pdf"


class TestValidateCaseLogAttachment:
    """validate_case_log_attachment() tests."""

    def test_valid_pdf(self) -> None:
        ok, err = validate_case_log_attachment("test.pdf", 1024)
        assert ok is True
        assert err is None

    def test_valid_docx(self) -> None:
        ok, err = validate_case_log_attachment("test.docx", 2048)
        assert ok is True
        assert err is None

    def test_unsupported_extension(self) -> None:
        ok, err = validate_case_log_attachment("test.exe", 1024)
        assert ok is False
        assert "不支持" in err  # type: ignore[operator]

    def test_no_extension(self) -> None:
        ok, err = validate_case_log_attachment("noext", 1024)
        assert ok is False
        assert "不支持" in err  # type: ignore[operator]

    def test_size_zero_unlimited(self) -> None:
        """CASE_LOG_MAX_FILE_SIZE=0 means no limit."""
        ok, err = validate_case_log_attachment("test.pdf", None)
        assert ok is True
        assert err is None

    def test_all_allowed_extensions(self) -> None:
        for ext in CASE_LOG_ALLOWED_EXTENSIONS:
            ok, err = validate_case_log_attachment(f"file{ext}", 100)
            assert ok is True, f"Extension {ext} should be allowed"

    def test_size_none(self) -> None:
        ok, err = validate_case_log_attachment("test.pdf", None)
        assert ok is True


class TestNormalizeCaseNumber:
    """normalize_case_number() tests."""

    def test_empty_returns_empty(self) -> None:
        assert normalize_case_number("") == ""

    def test_none_returns_empty(self) -> None:
        assert normalize_case_number(None) == ""  # type: ignore[arg-type]

    def test_parens_replaced(self) -> None:
        result = normalize_case_number("(2024)京01民初1号")
        assert "(" not in result
        assert ")" not in result
        assert "（" in result

    def test_square_brackets_replaced(self) -> None:
        result = normalize_case_number("[2024]京01民初1号")
        assert "[" not in result
        assert "]" not in result

    def test_curly_quotes_replaced(self) -> None:
        result = normalize_case_number("〔2024〕京01民初1号")
        assert "〔" not in result
        assert "〕" not in result

    def test_spaces_stripped(self) -> None:
        result = normalize_case_number("2024 京 01 民 初 1 号")
        assert " " not in result

    def test_fullwidth_space_stripped(self) -> None:
        result = normalize_case_number("2024　京01民初1号")
        assert "　" not in result

    def test_ensure_hao_adds_hao(self) -> None:
        result = normalize_case_number("(2024)京01民初1", ensure_hao=True)
        assert result.endswith("号")

    def test_ensure_hao_no_duplicate(self) -> None:
        result = normalize_case_number("(2024)京01民初1号", ensure_hao=True)
        assert result.endswith("号")
        assert not result.endswith("号号")

    def test_no_ensure_hao(self) -> None:
        result = normalize_case_number("(2024)京01民初1", ensure_hao=False)
        assert not result.endswith("号")


class TestCaseLogAllowedExtensions:
    """CASE_LOG_ALLOWED_EXTENSIONS constant checks."""

    def test_contains_pdf(self) -> None:
        assert ".pdf" in CASE_LOG_ALLOWED_EXTENSIONS

    def test_contains_doc_formats(self) -> None:
        assert ".doc" in CASE_LOG_ALLOWED_EXTENSIONS
        assert ".docx" in CASE_LOG_ALLOWED_EXTENSIONS

    def test_contains_image_formats(self) -> None:
        assert ".jpg" in CASE_LOG_ALLOWED_EXTENSIONS
        assert ".jpeg" in CASE_LOG_ALLOWED_EXTENSIONS
        assert ".png" in CASE_LOG_ALLOWED_EXTENSIONS

    def test_does_not_contain_exe(self) -> None:
        assert ".exe" not in CASE_LOG_ALLOWED_EXTENSIONS


class TestFixSqliteOrphanContractFk:
    """fix_sqlite_orphan_contract_fk() tests."""

    @patch("django.db.connection")
    def test_sqlite_executes_cleanup(self, mock_conn: Any) -> None:
        mock_conn.vendor = "sqlite"
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        fix_sqlite_orphan_contract_fk()
        mock_cursor.execute.assert_called_once()

    @patch("django.db.connection")
    def test_postgresql_skips_cleanup(self, mock_conn: Any) -> None:
        mock_conn.vendor = "postgresql"
        fix_sqlite_orphan_contract_fk()
        mock_conn.cursor.assert_not_called()
