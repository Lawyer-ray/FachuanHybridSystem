"""Batch7 coverage tests for apps.evidence."""
from __future__ import annotations

import io
import pathlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence.models.enums import (
    EvidenceDirection,
    EvidenceType,
    OriginalStatus,
)
from apps.evidence.models import (
    LIST_TYPE_ORDER,
    LIST_TYPE_PREVIOUS,
    MergeStatus,
)


# ── EvidenceDirection ───────────────────────────────────────────────────────


class TestEvidenceDirection:
    def test_our(self) -> None:
        assert EvidenceDirection.OUR == "our"

    def test_opponent(self) -> None:
        assert EvidenceDirection.OPPONENT == "opponent"

    def test_court(self) -> None:
        assert EvidenceDirection.COURT == "court"

    def test_choices_count(self) -> None:
        assert len(EvidenceDirection.choices) == 3


# ── EvidenceType ────────────────────────────────────────────────────────────


class TestEvidenceType:
    def test_documentary(self) -> None:
        assert EvidenceType.DOCUMENTARY == "documentary"

    def test_physical(self) -> None:
        assert EvidenceType.PHYSICAL == "physical"

    def test_audiovisual(self) -> None:
        assert EvidenceType.AUDIOVISUAL == "audiovisual"

    def test_electronic(self) -> None:
        assert EvidenceType.ELECTRONIC == "electronic"

    def test_witness(self) -> None:
        assert EvidenceType.WITNESS == "witness"

    def test_appraisal(self) -> None:
        assert EvidenceType.APPRAISAL == "appraisal"

    def test_inspection(self) -> None:
        assert EvidenceType.INSPECTION == "inspection"

    def test_statement(self) -> None:
        assert EvidenceType.STATEMENT == "statement"

    def test_choices_count(self) -> None:
        assert len(EvidenceType.choices) == 8


# ── OriginalStatus ──────────────────────────────────────────────────────────


class TestOriginalStatus:
    def test_has_original(self) -> None:
        assert OriginalStatus.HAS_ORIGINAL == "has_original"

    def test_copy_only(self) -> None:
        assert OriginalStatus.COPY_ONLY == "copy_only"

    def test_electronic(self) -> None:
        assert OriginalStatus.ELECTRONIC == "electronic"


# ── List type constants ─────────────────────────────────────────────────────


class TestListTypeConstants:
    def test_list_type_previous_is_dict(self) -> None:
        assert isinstance(LIST_TYPE_PREVIOUS, dict)

    def test_list_type_order_is_dict(self) -> None:
        assert isinstance(LIST_TYPE_ORDER, dict)

    def test_list_type_order_has_entries(self) -> None:
        assert len(LIST_TYPE_ORDER) > 0

    def test_list_type_previous_has_entries(self) -> None:
        assert len(LIST_TYPE_PREVIOUS) > 0


# ── MergeStatus ─────────────────────────────────────────────────────────────


class TestMergeStatus:
    def test_is_string_choices(self) -> None:
        assert hasattr(MergeStatus, "choices")


# ── pdf_utils ───────────────────────────────────────────────────────────────


from apps.evidence.services.infrastructure.pdf_utils import (
    _read_source_bytes,
    get_pdf_page_count,
    get_pdf_page_count_with_error,
)
from apps.core.utils.path import Path as AppPath


class TestPdfUtils:
    def test_read_source_bytes_none_raises(self) -> None:
        with pytest.raises(ValueError, match="source is None"):
            _read_source_bytes(None)

    def test_read_source_bytes_raw(self) -> None:
        data = b"hello"
        assert _read_source_bytes(data) == b"hello"

    def test_read_source_bytes_bytearray(self) -> None:
        data = bytearray(b"hello")
        assert _read_source_bytes(data) == b"hello"

    def test_read_source_bytes_from_path(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        # Use the app's Path class
        app_path = AppPath(str(f))
        result = _read_source_bytes(app_path)
        assert result == b"hello"

    def test_read_source_bytes_from_str_path(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = _read_source_bytes(str(f))
        assert result == b"hello"

    def test_read_source_bytes_from_file_like(self) -> None:
        buf = io.BytesIO(b"hello")
        result = _read_source_bytes(buf)
        assert result == b"hello"

    def test_read_source_bytes_unsupported_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported source type"):
            _read_source_bytes(12345)
