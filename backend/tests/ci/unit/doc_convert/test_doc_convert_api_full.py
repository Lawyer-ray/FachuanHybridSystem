from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.doc_convert.api.doc_convert_api import (
    _build_mbid_list_response,
    _check_znszj_enabled,
    _get_doc_convert_service,
    convert_document,
    get_mbid_list,
)
from apps.doc_convert.constants import MbidDefinition
from apps.doc_convert.exceptions import ZnszjDisabledError, ZnszjNotConfiguredError


class TestCheckZnszjEnabled:

    def test_enabled_does_not_raise(self):
        with patch("apps.doc_convert.api.doc_convert_api.settings") as mock_settings:
            mock_settings.ZNSZJ_ENABLED = True
            _check_znszj_enabled()

    def test_disabled_raises(self):
        with patch("apps.doc_convert.api.doc_convert_api.settings") as mock_settings:
            mock_settings.ZNSZJ_ENABLED = False
            with pytest.raises(ZnszjDisabledError):
                _check_znszj_enabled()

    def test_missing_attr_raises(self):
        with patch("apps.doc_convert.api.doc_convert_api.settings") as mock_settings:
            del mock_settings.ZNSZJ_ENABLED
            with pytest.raises(ZnszjDisabledError):
                _check_znszj_enabled()


class TestGetDocConvertService:

    def test_returns_service(self):
        mock_client = MagicMock()
        with patch("apps.doc_convert.api.doc_convert_api.get_znszj_client", return_value=mock_client):
            svc = _get_doc_convert_service()
            assert svc._client is mock_client

    def test_none_client_raises(self):
        with patch("apps.doc_convert.api.doc_convert_api.get_znszj_client", return_value=None):
            with pytest.raises(ZnszjNotConfiguredError):
                _get_doc_convert_service()


class TestBuildMbidListResponse:

    def test_builds_response(self):
        grouped = {
            "cat1": [MbidDefinition(mbid="a", name="A", category="cat1")],
            "cat2": [MbidDefinition(mbid="b", name="B", category="cat2")],
        }
        resp = _build_mbid_list_response(grouped)
        assert len(resp.categories) == 2
        cat_names = {c.category for c in resp.categories}
        assert cat_names == {"cat1", "cat2"}

    def test_empty_grouped(self):
        resp = _build_mbid_list_response({})
        assert len(resp.categories) == 0


class TestConvertDocumentEndpoint:

    def test_disabled_raises(self):
        with patch("apps.doc_convert.api.doc_convert_api._check_znszj_enabled", side_effect=ZnszjDisabledError):
            with pytest.raises(ZnszjDisabledError):
                convert_document(MagicMock(), file=MagicMock(), mbid="mjjdqsz")

    def test_success_returns_http_response(self):
        mock_file = MagicMock()
        mock_file.read.return_value = b"result_bytes"
        mock_file.name = "test.docx"

        mock_service = MagicMock()
        mock_service.convert_document.return_value = b"result_bytes"

        with patch("apps.doc_convert.api.doc_convert_api._check_znszj_enabled"):
            with patch("apps.doc_convert.api.doc_convert_api._get_doc_convert_service", return_value=mock_service):
                resp = convert_document(MagicMock(), file=mock_file, mbid="mjjdqsz")
                assert resp.status_code == 200
                assert b"result_bytes" in resp.content
                assert "attachment" in resp["Content-Disposition"]
