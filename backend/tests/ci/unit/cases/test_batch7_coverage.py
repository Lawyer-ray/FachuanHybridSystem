"""Batch7 coverage tests for apps.cases."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.utils import (
    CASE_LOG_ALLOWED_EXTENSIONS,
    _basename,
    get_file_extension_lower,
    normalize_case_number,
    validate_case_log_attachment,
)


# ── _basename ───────────────────────────────────────────────────────────────


class TestBasename:
    def test_simple_filename(self) -> None:
        assert _basename("test.pdf") == "test.pdf"

    def test_unix_path(self) -> None:
        assert _basename("/home/user/test.pdf") == "test.pdf"

    def test_windows_path(self) -> None:
        assert _basename("C:\\Users\\test\\file.docx") == "file.docx"

    def test_mixed_separators(self) -> None:
        assert _basename("C:\\Users/test\\file.pdf") == "file.pdf"

    def test_empty_string(self) -> None:
        assert _basename("") == ""

    def test_none_input(self) -> None:
        assert _basename(None) == ""

    def test_just_slash(self) -> None:
        assert _basename("/") == ""


# ── get_file_extension_lower ────────────────────────────────────────────────


class TestGetFileExtensionLower:
    def test_pdf_extension(self) -> None:
        assert get_file_extension_lower("test.PDF") == ".pdf"

    def test_docx_extension(self) -> None:
        assert get_file_extension_lower("report.DOCX") == ".docx"

    def test_no_extension(self) -> None:
        assert get_file_extension_lower("noext") == ""

    def test_hidden_file_no_ext(self) -> None:
        assert get_file_extension_lower(".gitignore") == ".gitignore"

    def test_dot_only(self) -> None:
        assert get_file_extension_lower(".") == ""

    def test_dot_dot(self) -> None:
        assert get_file_extension_lower("..") == ""

    def test_empty_string(self) -> None:
        assert get_file_extension_lower("") == ""

    def test_path_with_extension(self) -> None:
        assert get_file_extension_lower("/dir/file.TXT") == ".txt"

    def test_multiple_dots(self) -> None:
        assert get_file_extension_lower("archive.tar.gz") == ".gz"


# ── validate_case_log_attachment ────────────────────────────────────────────


class TestValidateCaseLogAttachment:
    def test_valid_pdf(self) -> None:
        ok, msg = validate_case_log_attachment("test.pdf", 1024)
        assert ok is True
        assert msg is None

    def test_unsupported_extension(self) -> None:
        ok, msg = validate_case_log_attachment("test.exe", 1024)
        assert ok is False
        assert msg == "不支持的文件类型"

    def test_no_size_limit(self) -> None:
        ok, msg = validate_case_log_attachment("test.pdf", 999999999)
        assert ok is True
        assert msg is None

    def test_no_size(self) -> None:
        ok, msg = validate_case_log_attachment("test.pdf", None)
        assert ok is True

    def test_all_allowed_extensions(self) -> None:
        for ext in CASE_LOG_ALLOWED_EXTENSIONS:
            ok, _ = validate_case_log_attachment(f"file{ext}", 100)
            assert ok is True


# ── normalize_case_number ───────────────────────────────────────────────────


class TestNormalizeCaseNumber:
    def test_empty_input(self) -> None:
        assert normalize_case_number("") == ""

    def test_none_input(self) -> None:
        assert normalize_case_number("") == ""

    def test_english_parens_to_chinese(self) -> None:
        result = normalize_case_number("(2024)粤01民初100号")
        assert "(" not in result
        assert ")" not in result
        assert "（" in result
        assert "）" in result

    def test_square_brackets_to_chinese_parens(self) -> None:
        result = normalize_case_number("[2024]粤01民初100号")
        assert "[" not in result
        assert "]" not in result
        assert "（" in result

    def test_fullwidth_parens_normalized(self) -> None:
        result = normalize_case_number("〔2024〕粤01民初100号")
        assert "〔" not in result
        assert "〕" not in result
        assert "（" in result

    def test_remove_spaces(self) -> None:
        result = normalize_case_number(" 2024 粤 01 民初 100 号 ")
        assert " " not in result

    def test_remove_fullwidth_space(self) -> None:
        result = normalize_case_number("2024　粤01民初100号")
        assert "　" not in result

    def test_ensure_hao_adds(self) -> None:
        result = normalize_case_number("（2024）粤01民初100", ensure_hao=True)
        assert result.endswith("号")

    def test_ensure_hao_already_has(self) -> None:
        result = normalize_case_number("（2024）粤01民初100号", ensure_hao=True)
        assert result.endswith("号")
        # 不会变成 "号号"
        assert not result.endswith("号号")


# ── cases domain validators ────────────────────────────────────────────────


from apps.cases.domain.validators import APPLICABLE_TYPES, is_applicable, normalize_stages


class TestIsApplicableExtra:
    def test_intl_type(self) -> None:
        assert is_applicable("intl") is True

    def test_numeric_string(self) -> None:
        assert is_applicable("123") is False

    def test_whitespace_only(self) -> None:
        assert is_applicable("  ") is False


class TestNormalizeStagesExtra:
    def test_valid_civil_stages(self) -> None:
        rep, cur = normalize_stages("civil", ["first_trial"], "first_trial")
        assert rep == ["first_trial"]
        assert cur == "first_trial"

    def test_empty_stages(self) -> None:
        rep, cur = normalize_stages("civil", [], None)
        assert rep == []
        assert cur is None

    def test_invalid_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_rep"):
            normalize_stages("civil", ["nonexistent_stage"], None)

    def test_cur_not_in_rep_raises(self) -> None:
        with pytest.raises(ValueError, match="cur_not_in_rep"):
            normalize_stages("civil", ["first_trial"], "second_trial")

    def test_strict_mode_with_stages_for_non_applicable_raises(self) -> None:
        with pytest.raises(ValueError, match="stages_not_applicable"):
            normalize_stages("special", ["first_trial"], None, strict=True)

    def test_invalid_cur_raises(self) -> None:
        # bogus_cur is not a valid stage, so it raises invalid_rep first
        with pytest.raises(ValueError, match="invalid_rep"):
            normalize_stages("civil", ["first_trial", "bogus_cur"], "bogus_cur")

    def test_cur_not_in_rep_valid_stages_raises(self) -> None:
        """current_stage is valid but not in representation_stages."""
        from apps.core.models.enums import CaseStage
        # Pick two valid stages
        valid_stages = [c[0] for c in CaseStage.choices]
        if len(valid_stages) >= 2:
            with pytest.raises(ValueError, match="cur_not_in_rep"):
                normalize_stages("civil", [valid_stages[0]], valid_stages[1])
