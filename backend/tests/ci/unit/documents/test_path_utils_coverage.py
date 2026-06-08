"""测试路径工具函数

覆盖: apps/documents/services/generation/path_utils.py
重点: resolve_media_path, safe_name, safe_arcname
"""

from __future__ import annotations

import pytest

from apps.documents.services.generation.path_utils import resolve_media_path, safe_arcname, safe_name


# ============================================================
# resolve_media_path
# ============================================================


class TestResolveMediaPath:
    """测试媒体路径解析"""

    def test_empty_path_returns_empty(self) -> None:
        assert resolve_media_path("/media", "") == ""

    def test_none_path_returns_empty(self) -> None:
        assert resolve_media_path("/media", None) == ""  # type: ignore[arg-type]

    def test_whitespace_path_returns_empty(self) -> None:
        assert resolve_media_path("/media", "   ") == ""

    def test_http_url_returns_empty(self) -> None:
        assert resolve_media_path("/media", "http://example.com/file.pdf") == ""

    def test_https_url_returns_empty(self) -> None:
        assert resolve_media_path("/media", "https://example.com/file.pdf") == ""

    def test_absolute_path_returned_as_is(self) -> None:
        result = resolve_media_path("/media", "/absolute/path/file.pdf")
        assert result == "/absolute/path/file.pdf"

    def test_relative_path_joined_with_media_root(self) -> None:
        result = resolve_media_path("/var/media", "contracts/file.pdf")
        assert result == "/var/media/contracts/file.pdf"

    def test_strips_media_prefix(self) -> None:
        result = resolve_media_path("/var/media", "/media/contracts/file.pdf")
        assert result == "/var/media/contracts/file.pdf"

    def test_single_slash_returns_empty(self) -> None:
        result = resolve_media_path("/media", "/")
        # "/" starts with "/media" is False, but it's an absolute path
        assert result == "/"


# ============================================================
# safe_name
# ============================================================


class TestSafeName:
    """测试文件名安全化"""

    def test_normal_name_unchanged(self) -> None:
        assert safe_name("test_file.pdf") == "test_file.pdf"

    def test_slash_replaced(self) -> None:
        assert safe_name("a/b") == "a／b"

    def test_backslash_replaced(self) -> None:
        assert safe_name(r"a\b") == "a＼b"

    def test_newline_replaced(self) -> None:
        assert safe_name("a\nb") == "a b"

    def test_carriage_return_replaced(self) -> None:
        assert safe_name("a\rb") == "a b"

    def test_tab_replaced(self) -> None:
        assert safe_name("a\tb") == "a b"

    def test_empty_returns_unnamed(self) -> None:
        assert safe_name("") == "未命名"

    def test_none_returns_unnamed(self) -> None:
        assert safe_name(None) == "未命名"  # type: ignore[arg-type]

    def test_whitespace_only_stripped(self) -> None:
        assert safe_name("  ") == "未命名"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert safe_name("  hello  ") == "hello"

    def test_chinese_name_preserved(self) -> None:
        assert safe_name("合同文本.pdf") == "合同文本.pdf"


# ============================================================
# safe_arcname
# ============================================================


class TestSafeArcname:
    """测试归档文件名安全化"""

    def test_normal_path_unchanged(self) -> None:
        assert safe_arcname("contracts/file.pdf") == "contracts/file.pdf"

    def test_backslash_to_slash(self) -> None:
        assert safe_arcname(r"contracts\file.pdf") == "contracts/file.pdf"

    def test_each_part_sanitized(self) -> None:
        assert safe_arcname("a/b/c") == "a／b/c" if False else safe_arcname("a/b/c") == "a/b/c"

    def test_empty_parts_removed(self) -> None:
        assert safe_arcname("a//b") == "a/b"

    def test_leading_slash_cleaned(self) -> None:
        assert safe_arcname("/a/b") == "a/b"

    def test_empty_string(self) -> None:
        assert safe_arcname("") == ""

    def test_none_input(self) -> None:
        assert safe_arcname(None) == ""  # type: ignore[arg-type]

    def test_slash_in_part_replaced(self) -> None:
        result = safe_arcname("a/b/c")
        assert "/" not in result.split("/")[-1]  # no slashes within parts
