"""Tests for refactored pure functions from documents/services/generation/."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

# Import the pure functions we extracted
from apps.documents.services.generation.path_utils import resolve_media_path, safe_name, safe_arcname
from apps.documents.services.generation.result import GenerationResult


class TestResolveMediaPath:
    """Tests for resolve_media_path pure function."""

    def test_empty_path_returns_empty(self):
        assert resolve_media_path("/media", "") == ""

    def test_none_path_returns_empty(self):
        assert resolve_media_path("/media", None) == ""

    def test_whitespace_path_returns_empty(self):
        assert resolve_media_path("/media", "   ") == ""

    def test_http_url_returns_empty(self):
        assert resolve_media_path("/media", "http://example.com/file.pdf") == ""

    def test_https_url_returns_empty(self):
        assert resolve_media_path("/media", "https://example.com/file.pdf") == ""

    def test_media_prefix_stripped(self):
        result = resolve_media_path("/var/media", "/media/uploads/file.pdf")
        assert result == "/var/media/uploads/file.pdf"

    def test_absolute_path_returned_as_is(self):
        result = resolve_media_path("/media", "/absolute/path/file.pdf")
        assert result == "/absolute/path/file.pdf"

    def test_relative_path_joined_with_root(self):
        result = resolve_media_path("/var/media", "uploads/file.pdf")
        assert result == "/var/media/uploads/file.pdf"

    def test_relative_path_no_leading_slash(self):
        result = resolve_media_path("/media", "file.pdf")
        assert result == "/media/file.pdf"


class TestSafeName:
    """Tests for safe_name pure function."""

    def test_empty_string_returns_unnamed(self):
        assert safe_name("") == "未命名"

    def test_none_returns_unnamed(self):
        assert safe_name(None) == "未命名"

    def test_whitespace_only_returns_unnamed(self):
        assert safe_name("   ") == "未命名"

    def test_normal_name_unchanged(self):
        assert safe_name("test.txt") == "test.txt"

    def test_slash_replaced(self):
        assert safe_name("a/b") == "a／b"

    def test_backslash_replaced(self):
        assert safe_name("a\\b") == "a＼b"

    def test_newline_replaced(self):
        assert safe_name("a\nb") == "a b"

    def test_carriage_return_replaced(self):
        assert safe_name("a\rb") == "a b"

    def test_tab_replaced(self):
        assert safe_name("a\tb") == "a b"

    def test_multiple_special_chars(self):
        assert safe_name("a/b\\c\nd") == "a／b＼c d"


class TestSafeArcname:
    """Tests for safe_arcname pure function."""

    def test_empty_string(self):
        assert safe_arcname("") == ""

    def test_none(self):
        assert safe_arcname(None) == ""

    def test_simple_name(self):
        assert safe_arcname("file.txt") == "file.txt"

    def test_forward_slash_preserved(self):
        assert safe_arcname("dir/file.txt") == "dir/file.txt"

    def test_backslash_converted_to_slash(self):
        assert safe_arcname("dir\\file.txt") == "dir/file.txt"

    def test_empty_segments_removed(self):
        assert safe_arcname("dir//file.txt") == "dir/file.txt"

    def test_trailing_slash_removed(self):
        assert safe_arcname("dir/file.txt/") == "dir/file.txt"

    def test_special_chars_in_path_segments(self):
        assert safe_arcname("a/b/c.txt") == "a/b/c.txt"


class TestGenerationResult:
    """Tests for GenerationResult dataclass validation."""

    def test_success_with_path(self):
        result = GenerationResult(success=True, file_path="/tmp/test.pdf", file_name="test.pdf")
        assert result.success is True
        assert result.file_path == "/tmp/test.pdf"

    def test_success_without_path_raises(self):
        with pytest.raises(ValueError, match="文件路径"):
            GenerationResult(success=True)

    def test_failure_with_error(self):
        result = GenerationResult(success=False, error_message="Some error")
        assert result.success is False
        assert result.error_message == "Some error"

    def test_failure_without_error_raises(self):
        with pytest.raises(ValueError, match="错误信息"):
            GenerationResult(success=False)

    def test_negative_duration_raises(self):
        with pytest.raises(ValueError, match="耗时"):
            GenerationResult(success=False, error_message="err", duration_ms=-1)

    def test_zero_duration_valid(self):
        result = GenerationResult(success=False, error_message="err", duration_ms=0)
        assert result.duration_ms == 0

    def test_positive_duration_valid(self):
        result = GenerationResult(success=True, file_path="/tmp/test.pdf", duration_ms=100)
        assert result.duration_ms == 100

    def test_default_duration_is_zero(self):
        result = GenerationResult(success=False, error_message="err")
        assert result.duration_ms == 0

    def test_success_with_all_fields(self):
        result = GenerationResult(
            success=True,
            file_path="/tmp/test.pdf",
            file_name="test.pdf",
            error_message=None,
            duration_ms=500,
        )
        assert result.file_name == "test.pdf"
        assert result.duration_ms == 500

    def test_failure_with_all_fields(self):
        result = GenerationResult(
            success=False,
            file_path=None,
            file_name=None,
            error_message="Failed",
            duration_ms=100,
        )
        assert result.error_message == "Failed"


class TestSafeArcnameEdgeCases:
    """Additional edge cases for safe_arcname."""

    def test_only_slashes(self):
        assert safe_arcname("///") == ""

    def test_single_file(self):
        assert safe_arcname("file.txt") == "file.txt"

    def test_deep_path(self):
        result = safe_arcname("a/b/c/d.txt")
        assert result == "a/b/c/d.txt"

    def test_mixed_separators(self):
        result = safe_arcname("a\\b/c.txt")
        assert result == "a/b/c.txt"


class TestResolveMediaPathEdgeCases:
    """Additional edge cases for resolve_media_path."""

    def test_media_prefix_without_following_slash(self):
        result = resolve_media_path("/var/media", "media/file.pdf")
        assert result == "/var/media/media/file.pdf"

    def test_ftp_protocol_not_filtered(self):
        result = resolve_media_path("/media", "ftp://server/file.pdf")
        assert result == "/media/ftp:/server/file.pdf"

    def test_relative_path_with_dots(self):
        result = resolve_media_path("/media", "../file.pdf")
        assert result == "/media/../file.pdf"
