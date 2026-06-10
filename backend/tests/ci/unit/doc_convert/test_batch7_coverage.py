"""Batch7 coverage tests for apps.doc_convert."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.doc_convert.constants import (
    MBID_DEFINITIONS,
    get_mbid_by_category,
    get_mbid_set,
)
from apps.doc_convert.exceptions import (
    ERROR_FILE_TOO_LARGE,
    ERROR_INVALID_FILE_TYPE,
    ERROR_INVALID_MBID,
    ERROR_ZNSZJ_DISABLED,
    ERROR_ZNSZJ_INVALID_RESPONSE,
    ERROR_ZNSZJ_NOT_CONFIGURED,
    ERROR_ZNSZJ_UNAVAILABLE,
    FileTooLargeError,
    InvalidFileTypeError,
    InvalidMbidError,
    ZnszjDisabledError,
    ZnszjInvalidResponseError,
    ZnszjNotConfiguredError,
    ZnszjUnavailableError,
)


# ── MBID constants ──────────────────────────────────────────────────────────


class TestMbidConstants:
    def test_mbid_definitions_not_empty(self) -> None:
        assert len(MBID_DEFINITIONS) > 0

    def test_mbid_definitions_have_required_fields(self) -> None:
        for item in MBID_DEFINITIONS:
            assert "mbid" in item
            assert "name" in item
            assert "category" in item

    def test_get_mbid_set(self) -> None:
        mbid_set = get_mbid_set()
        assert isinstance(mbid_set, set)
        assert len(mbid_set) == len(MBID_DEFINITIONS)
        assert "mjjdqsz" in mbid_set

    def test_get_mbid_by_category(self) -> None:
        by_cat = get_mbid_by_category()
        assert "起诉状" in by_cat
        assert "答辩状" in by_cat
        assert "申请书" in by_cat

    def test_categories_covered(self) -> None:
        by_cat = get_mbid_by_category()
        categories = set(by_cat.keys())
        assert "起诉状" in categories
        assert "答辩状" in categories
        assert "申请书" in categories
        assert "其他" in categories


# ── Error codes ─────────────────────────────────────────────────────────────


class TestErrorCodes:
    def test_disabled_code(self) -> None:
        assert ERROR_ZNSZJ_DISABLED == "ZNSZJ_DISABLED"

    def test_not_configured_code(self) -> None:
        assert ERROR_ZNSZJ_NOT_CONFIGURED == "ZNSZJ_NOT_CONFIGURED"

    def test_invalid_file_type_code(self) -> None:
        assert ERROR_INVALID_FILE_TYPE == "INVALID_FILE_TYPE"

    def test_invalid_mbid_code(self) -> None:
        assert ERROR_INVALID_MBID == "INVALID_MBID"

    def test_file_too_large_code(self) -> None:
        assert ERROR_FILE_TOO_LARGE == "FILE_TOO_LARGE"


# ── Exception classes ───────────────────────────────────────────────────────


class TestZnszjDisabledError:
    def test_message(self) -> None:
        err = ZnszjDisabledError()
        assert "未启用" in err.message

    def test_status(self) -> None:
        assert ZnszjDisabledError.status == 403


class TestZnszjNotConfiguredError:
    def test_message(self) -> None:
        err = ZnszjNotConfiguredError()
        assert "未配置" in err.message

    def test_status(self) -> None:
        assert ZnszjNotConfiguredError.status == 503


class TestInvalidFileTypeError:
    def test_message_includes_extensions(self) -> None:
        err = InvalidFileTypeError(filename="test.xyz", allowed_extensions=[".pdf", ".docx"])
        assert ".pdf" in err.message
        assert ".docx" in err.message


class TestInvalidMbidError:
    def test_message_includes_mbid(self) -> None:
        err = InvalidMbidError(mbid="bad_mbid")
        assert "bad_mbid" in err.message


class TestFileTooLargeError:
    def test_message_includes_sizes(self) -> None:
        err = FileTooLargeError(size_mb=25.5, max_size_mb=20)
        assert "25.50" in err.message
        assert "20" in err.message


class TestZnszjUnavailableError:
    def test_default_message(self) -> None:
        err = ZnszjUnavailableError()
        assert "不可用" in err.message

    def test_with_detail(self) -> None:
        err = ZnszjUnavailableError(detail="connection refused")
        assert err.errors.get("detail") == "connection refused"

    def test_status(self) -> None:
        assert ZnszjUnavailableError.status == 502


class TestZnszjInvalidResponseError:
    def test_default_message(self) -> None:
        err = ZnszjInvalidResponseError()
        assert "异常" in err.message

    def test_status(self) -> None:
        assert ZnszjInvalidResponseError.status == 502
