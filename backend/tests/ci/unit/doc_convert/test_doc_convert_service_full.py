from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.doc_convert.constants import MbidDefinition, get_mbid_by_category, get_mbid_set
from apps.doc_convert.exceptions import (
    FileTooLargeError,
    InvalidFileTypeError,
    InvalidMbidError,
    ZnszjUnavailableError,
    ZnszjInvalidResponseError,
)
from apps.doc_convert.services.doc_convert_service import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    DocConvertService,
)


class TestDocConvertServiceGetMbidList:

    def test_returns_grouped_dict(self):
        svc = DocConvertService(znszj_client=MagicMock())
        result = svc.get_mbid_list()
        assert isinstance(result, dict)
        assert len(result) > 0
        for cat, items in result.items():
            assert isinstance(cat, str)
            assert isinstance(items, list)
            for item in items:
                assert "mbid" in item
                assert "name" in item


class TestDocConvertServiceConvertDocument:

    def test_invalid_extension_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        with pytest.raises(InvalidFileTypeError):
            svc.convert_document(file_content=b"data", filename="test.txt", mbid="mjjdqsz")

    def test_invalid_mbid_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        with pytest.raises(InvalidMbidError):
            svc.convert_document(file_content=b"data", filename="test.docx", mbid="INVALID_MBID")

    def test_file_too_large_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        large_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileTooLargeError):
            svc.convert_document(file_content=large_content, filename="big.docx", mbid="mjjdqsz")

    def test_success_docx(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"converted"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=b"data", filename="test.docx", mbid="mjjdqsz")
        assert result == b"converted"
        mock_client.convert_document.assert_called_once_with(
            file_content=b"data", filename="test.docx", mbid="mjjdqsz"
        )

    def test_success_doc(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=b"data", filename="test.doc", mbid="lhjfqsz")
        assert result == b"ok"

    def test_success_pdf(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"pdf_result"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=b"data", filename="test.pdf", mbid="mmhtqsz")
        assert result == b"pdf_result"

    def test_znszj_unavailable_error_reraised(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = ZnszjUnavailableError(detail="down")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjUnavailableError):
            svc.convert_document(file_content=b"data", filename="test.docx", mbid="mjjdqsz")

    def test_znszj_invalid_response_reraised(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = ZnszjInvalidResponseError(detail="bad format")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjInvalidResponseError):
            svc.convert_document(file_content=b"data", filename="test.docx", mbid="mjjdqsz")

    def test_generic_exception_wrapped(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = RuntimeError("unexpected")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjUnavailableError):
            svc.convert_document(file_content=b"data", filename="test.docx", mbid="mjjdqsz")

    def test_max_file_size_exactly_at_limit(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        content = b"x" * MAX_FILE_SIZE_BYTES
        result = svc.convert_document(file_content=content, filename="test.docx", mbid="mjjdqsz")
        assert result == b"ok"

    def test_case_insensitive_extension(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=b"data", filename="test.DOCX", mbid="mjjdqsz")
        assert result == b"ok"


class TestConstants:

    def test_allowed_extensions(self):
        assert ".docx" in ALLOWED_EXTENSIONS
        assert ".doc" in ALLOWED_EXTENSIONS
        assert ".pdf" in ALLOWED_EXTENSIONS

    def test_max_file_size(self):
        assert MAX_FILE_SIZE_MB == 20
        assert MAX_FILE_SIZE_BYTES == 20 * 1024 * 1024
