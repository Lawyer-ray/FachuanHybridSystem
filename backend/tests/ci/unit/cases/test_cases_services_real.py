"""cases 模块真实执行测试 - 覆盖 utils, validators, case_service 逻辑等。"""
from __future__ import annotations

import pytest

from apps.cases.utils import (
    CASE_LOG_ALLOWED_EXTENSIONS,
    _basename,
    get_file_extension_lower,
    normalize_case_number,
    validate_case_log_attachment,
)


# ============================================================
# cases/utils.py - get_file_extension_lower
# ============================================================


class TestGetFileExtension:
    def test_pdf_extension(self) -> None:
        assert get_file_extension_lower("document.pdf") == ".pdf"

    def test_docx_extension(self) -> None:
        assert get_file_extension_lower("report.docx") == ".docx"

    def test_no_extension(self) -> None:
        assert get_file_extension_lower("noext") == ""

    def test_hidden_file(self) -> None:
        assert get_file_extension_lower(".gitignore") == ".gitignore"

    def test_dot_only(self) -> None:
        assert get_file_extension_lower(".") == ""

    def test_dot_dot(self) -> None:
        assert get_file_extension_lower("..") == ""

    def test_empty_string(self) -> None:
        assert get_file_extension_lower("") == ""

    def test_none_input(self) -> None:
        assert get_file_extension_lower(None) == ""

    def test_path_with_directory(self) -> None:
        assert get_file_extension_lower("/path/to/file.PDF") == ".pdf"

    def test_multiple_dots(self) -> None:
        assert get_file_extension_lower("archive.tar.gz") == ".gz"


# ============================================================
# cases/utils.py - _basename
# ============================================================


class TestBasename:
    def test_simple_filename(self) -> None:
        assert _basename("file.txt") == "file.txt"

    def test_path_with_slashes(self) -> None:
        assert _basename("/path/to/file.txt") == "file.txt"

    def test_backslash_path(self) -> None:
        assert _basename("C:\\Users\\file.txt") == "file.txt"

    def test_none_input(self) -> None:
        assert _basename(None) == ""

    def test_empty(self) -> None:
        assert _basename("") == ""


# ============================================================
# cases/utils.py - validate_case_log_attachment
# ============================================================


class TestValidateCaseLogAttachment:
    def test_valid_pdf(self) -> None:
        valid, error = validate_case_log_attachment("test.pdf", 1024)
        assert valid is True
        assert error is None

    def test_invalid_extension(self) -> None:
        valid, error = validate_case_log_attachment("test.exe", 1024)
        assert valid is False
        assert "不支持" in error

    def test_valid_docx(self) -> None:
        valid, error = validate_case_log_attachment("test.docx", 1024)
        assert valid is True

    def test_valid_jpg(self) -> None:
        valid, error = validate_case_log_attachment("photo.jpg", 1024)
        assert valid is True

    def test_valid_png(self) -> None:
        valid, error = validate_case_log_attachment("image.png", 1024)
        assert valid is True

    def test_all_allowed_extensions(self) -> None:
        for ext in CASE_LOG_ALLOWED_EXTENSIONS:
            valid, _ = validate_case_log_attachment(f"file{ext}", 1024)
            assert valid is True, f"Extension {ext} should be allowed"


# ============================================================
# cases/utils.py - normalize_case_number
# ============================================================


class TestNormalizeCaseNumber:
    def test_empty(self) -> None:
        assert normalize_case_number("") == ""

    def test_parentheses_conversion(self) -> None:
        result = normalize_case_number("(2026)京01民初123号")
        assert "(" not in result
        assert ")" not in result
        assert "（" in result
        assert "）" in result

    def test_square_bracket_conversion(self) -> None:
        result = normalize_case_number("[2026]京01民初123号")
        assert "[" not in result
        assert "]" not in result

    def test_ensure_hao(self) -> None:
        result = normalize_case_number("（2026）京01民初123", ensure_hao=True)
        assert result.endswith("号")

    def test_ensure_hao_already_has(self) -> None:
        result = normalize_case_number("（2026）京01民初123号", ensure_hao=True)
        assert result.endswith("号")
        # Should not add "号" twice
        assert result.count("号") == 1

    def test_spaces_removal(self) -> None:
        result = normalize_case_number("（2026） 京 01 民初 123 号")
        assert " " not in result

    def test_unicode_space_removal(self) -> None:
        result = normalize_case_number("（2026）　京01民初123号")
        assert "　" not in result

    def test_fullwidth_parentheses(self) -> None:
        result = normalize_case_number("〔2026〕京01民初123号")
        assert "〔" not in result
        assert "〕" not in result


# ============================================================
# cases/utils.py - constants
# ============================================================


class TestCaseConstants:
    def test_allowed_extensions_not_empty(self) -> None:
        assert len(CASE_LOG_ALLOWED_EXTENSIONS) > 0

    def test_allowed_extensions_lowercase(self) -> None:
        for ext in CASE_LOG_ALLOWED_EXTENSIONS:
            assert ext == ext.lower()


# ============================================================
# cases/models (integration tests)
# ============================================================


@pytest.mark.django_db
class TestCaseModels:
    def test_case_creation(self) -> None:
        from apps.cases.models import Case

        case = Case.objects.create(name="Test Case")
        assert case.pk is not None
        assert case.name == "Test Case"

    def test_case_str(self) -> None:
        from apps.cases.models import Case

        case = Case.objects.create(name="Display Name")
        assert str(case) == "Display Name"

    def test_case_default_status(self) -> None:
        from apps.cases.models import Case

        case = Case.objects.create(name="Status Test")
        assert case.status is not None


@pytest.mark.django_db
class TestCaseLogModels:
    def test_caselog_creation(self) -> None:
        from apps.cases.models import Case, CaseLog
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="Log Test Firm")
        lawyer = Lawyer.objects.create_user(
            username="logactor",
            password="testpass123",
            real_name="Log Actor",
            law_firm=firm,
        )
        case = Case.objects.create(name="Log Test Case")
        log = CaseLog.objects.create(
            case=case,
            content="Test content",
            actor=lawyer,
        )
        assert log.pk is not None
        assert log.case_id == case.pk
        assert log.content == "Test content"


@pytest.mark.django_db
class TestCasePartyModels:
    def test_case_party_creation(self, db) -> None:
        from apps.cases.models import Case, CaseParty
        from apps.client.models import Client

        case = Case.objects.create(name="Party Test Case")
        client = Client.objects.create(name="Party Client", client_type=Client.NATURAL)
        party = CaseParty.objects.create(
            case=case,
            client=client,
            legal_status="plaintiff",
        )
        assert party.pk is not None
        assert party.legal_status == "plaintiff"
