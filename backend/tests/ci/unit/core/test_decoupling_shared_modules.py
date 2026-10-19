"""解耦（2026-10-19）新增 core 共享模块的单测。

覆盖：upload_paths 新增的 safe_name / safe_arcname / replace_illegal_filename_chars /
sanitize_filename_part、security.ownership.created_by_ownership_q、
utils.csv_safety.csv_safe_cell、filesystem.path_confinement.is_within。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from django.db.models import Q

from apps.core.filesystem.path_confinement import is_within
from apps.core.filesystem.upload_paths import (
    replace_illegal_filename_chars,
    safe_arcname,
    safe_name,
    sanitize_filename_part,
)
from apps.core.security.ownership import created_by_ownership_q
from apps.core.utils.csv_safety import csv_safe_cell


class TestSafeName:
    def test_display_name_keeps_readable(self):
        assert safe_name("甲/乙\\丙") == "甲／乙＼丙"
        assert safe_name("a\nb\rc\td") == "a b c d"

    def test_empty_fallback_and_collapse(self):
        assert safe_name("") == "未命名"
        assert safe_name("  x　 y ", collapse_whitespace=True) == "x y"
        # 默认不压空白（documents 侧既有口径）
        assert safe_name("a  b") == "a  b"


class TestSafeArcname:
    def test_dots_and_drive_stripped(self):
        assert safe_arcname("../evil/x.pdf") == "evil/x.pdf"
        assert safe_arcname("C:\\evil\\x.pdf") == "evil/x.pdf"
        assert safe_arcname("/abs/path/../x") == "abs/path/x"

    def test_segments_sanitized(self):
        assert safe_arcname("a/../b/./c") == "a/b/c"
        assert safe_arcname("") == ""


class TestReplaceIllegalFilenameChars:
    def test_collapsed_runs_replaced(self):
        assert replace_illegal_filename_chars('a<>?:"/\\|b') == "a_b"
        assert replace_illegal_filename_chars(" x\ny ") == "x_y"

    def test_all_illegal_collapses_to_replacement(self):
        # 连续非法段替换为单个 replacement 后仅剩该字符；空兜底由调用方处理
        assert replace_illegal_filename_chars("///") == "_"


class TestSanitizeFilenamePart:
    def test_removes_illegal_parens_control_and_edges(self):
        # 全角冒号不在 ASCII 非法字符集内，保留
        assert sanitize_filename_part("判決(一审)：甲?") == "判決一审：甲"
        assert sanitize_filename_part(" .名称. ") == "名称"
        assert sanitize_filename_part("") == ""


class TestCreatedByOwnershipQ:
    def test_admin_returns_none(self):
        assert created_by_ownership_q(SimpleNamespace(is_admin=True, is_superuser=False)) is None
        assert created_by_ownership_q(SimpleNamespace(is_admin=False, is_superuser=True)) is None

    def test_regular_user_gets_created_by_or_null(self):
        user = SimpleNamespace(is_admin=False, is_superuser=False, id=7)
        q = created_by_ownership_q(user)
        expected = Q(created_by=user) | Q(created_by__isnull=True)
        assert q is not None and str(q) == str(expected)

    def test_include_legacy_null_false(self):
        user = SimpleNamespace(is_admin=False, is_superuser=False, id=7)
        assert str(created_by_ownership_q(user, include_legacy_null=False)) == str(Q(created_by=user))


class TestCsvSafeCell:
    def test_formula_prefixes_quoted(self):
        for prefix in ("=", "+", "@"):
            assert csv_safe_cell(prefix + "cmd|' /C calc'!A0") == "'" + prefix + "cmd|' /C calc'!A0"

    def test_negative_numbers_not_quoted(self):
        assert csv_safe_cell("-1234.50") == "-1234.50"
        assert csv_safe_cell("-12,345") == "-12,345"

    def test_other_dash_text_quoted(self):
        assert csv_safe_cell("- 先行判决") == "'- 先行判决"

    def test_plain_and_empty_untouched(self):
        assert csv_safe_cell("（20XX）粤AA民终X号") == "（20XX）粤AA民终X号"  # privacy-allow 虚构案号
        assert csv_safe_cell("") == ""
        assert csv_safe_cell(None) == ""


class TestIsWithin:
    def test_within_and_outside(self):
        root = Path("/media/root")
        assert is_within(root, Path("/media/root/a/b.pdf"))
        assert not is_within(root, Path("/media/root2/b.pdf"))
        assert not is_within(root, Path("/etc/passwd"))

    def test_exact_root_is_within(self):
        root = Path("/media/root")
        assert is_within(root, root)
