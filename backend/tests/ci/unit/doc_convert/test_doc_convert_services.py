"""Tests for doc_convert services."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from apps.doc_convert.exceptions import InvalidFileTypeError, InvalidMbidError, FileTooLargeError


class TestDocConvertServiceConvertDocument:
    def _make_service(self, client=None):
        from apps.doc_convert.services.doc_convert_service import DocConvertService
        return DocConvertService(znszj_client=client or MagicMock())

    def test_invalid_extension_raises(self):
        svc = self._make_service()
        with pytest.raises(InvalidFileTypeError):
            svc.convert_document(file_content=b"data", filename="test.txt", mbid="mb001")

    def test_invalid_mbid_raises(self):
        svc = self._make_service()
        with pytest.raises(InvalidMbidError):
            svc.convert_document(file_content=b"data", filename="test.docx", mbid="invalid_mbid")

    def test_too_large_raises(self):
        svc = self._make_service()
        from apps.doc_convert.services.doc_convert_service import MAX_FILE_SIZE_BYTES
        from apps.doc_convert.constants import get_mbid_set
        valid_mbids = get_mbid_set()
        if not valid_mbids:
            pytest.skip("No valid mbids available")
        mbid = list(valid_mbids)[0]
        large_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileTooLargeError):
            svc.convert_document(file_content=large_content, filename="test.docx", mbid=mbid)

    def test_valid_conversion(self):
        from apps.doc_convert.constants import get_mbid_set
        valid_mbids = get_mbid_set()
        if not valid_mbids:
            pytest.skip("No valid mbids available")
        mbid = list(valid_mbids)[0]
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"converted"
        svc = self._make_service(client=mock_client)
        result = svc.convert_document(file_content=b"data", filename="test.docx", mbid=mbid)
        assert result == b"converted"

    def test_get_mbid_list(self):
        svc = self._make_service()
        result = svc.get_mbid_list()
        assert isinstance(result, dict)
