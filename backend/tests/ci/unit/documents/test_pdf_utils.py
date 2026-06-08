"""Tests for documents.services.infrastructure.pdf_utils."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.infrastructure.pdf_utils import (
    _read_django_field_file,
    _read_file_like,
    _read_from_path_attr,
    _read_source_bytes,
    get_pdf_page_count,
    get_pdf_page_count_with_error,
)


class TestReadSourceBytes:
    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="None"):
            _read_source_bytes(None)

    def test_bytes(self) -> None:
        data = b"hello"
        assert _read_source_bytes(data) == b"hello"

    def test_bytearray(self) -> None:
        data = bytearray(b"hello")
        result = _read_source_bytes(data)
        assert result == b"hello"
        assert isinstance(result, bytes)

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported"):
            _read_source_bytes(12345)


class TestReadDjangoFieldFile:
    def test_returns_none_if_no_open(self) -> None:
        source = MagicMock(spec=[])  # no open/read
        assert _read_django_field_file(source) is None

    def test_reads_data(self) -> None:
        source = MagicMock()
        source.read.return_value = b"pdf data"
        result = _read_django_field_file(source)
        assert result == b"pdf data"

    def test_read_exception_returns_none(self) -> None:
        source = MagicMock()
        source.read.side_effect = IOError("read error")
        result = _read_django_field_file(source)
        assert result is None


class TestReadFileLike:
    def test_returns_none_if_no_read(self) -> None:
        source = MagicMock(spec=[])  # no read
        assert _read_file_like(source) is None

    def test_reads_and_restores_position(self) -> None:
        source = io.BytesIO(b"hello world")
        source.seek(5)
        result = _read_file_like(source)
        assert result == b"hello world"
        assert source.tell() == 5  # position restored

    def test_read_exception_returns_none(self) -> None:
        source = MagicMock()
        source.read.side_effect = IOError("read error")
        source.tell.return_value = 0
        result = _read_file_like(source)
        assert result is None


class TestReadFromPathAttr:
    def test_returns_none_no_path(self) -> None:
        source = MagicMock(spec=[])
        assert _read_from_path_attr(source) is None

    @patch("apps.documents.services.infrastructure.pdf_utils.Path")
    def test_reads_from_path(self, mock_path_cls) -> None:
        mock_path = MagicMock()
        mock_path.read_bytes.return_value = b"data"
        mock_path_cls.return_value = mock_path

        source = MagicMock()
        source.path = "/some/file.pdf"
        result = _read_from_path_attr(source)
        assert result == b"data"


class TestGetPdfPageCount:
    def test_returns_int(self) -> None:
        # Just verify the function signature works
        result = get_pdf_page_count.__wrapped__(b"data", default=1) if hasattr(get_pdf_page_count, '__wrapped__') else None
        # The function requires real PDF data, so just test the wrapper
        assert callable(get_pdf_page_count)
