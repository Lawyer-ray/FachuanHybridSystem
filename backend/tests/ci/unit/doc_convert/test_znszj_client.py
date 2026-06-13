"""Tests for plugins.doc_convert.znszj_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

pytest.importorskip("plugins.doc_convert", reason="doc_convert plugin not installed")

from apps.doc_convert.exceptions import ZnszjInvalidResponseError, ZnszjUnavailableError  # noqa: E402
from plugins.doc_convert.znszj_client import (  # noqa: E402
    GDZQFY_URL,
    TIMEOUT,
    ZNSZJ_BASE,
    ZnszjClient,
    _make_client,
)


class TestMakeClient:
    @patch.dict("os.environ", {"HTTPS_PROXY": "http://proxy:8080"})
    def test_with_proxy(self) -> None:
        client = _make_client()
        assert isinstance(client, httpx.Client)
        client.close()

    @patch.dict("os.environ", {}, clear=True)
    def test_without_proxy(self) -> None:
        client = _make_client()
        assert isinstance(client, httpx.Client)
        client.close()

    @patch.dict("os.environ", {"https_proxy": "http://proxy:8080"})
    def test_lowercase_proxy(self) -> None:
        client = _make_client()
        assert isinstance(client, httpx.Client)
        client.close()


class TestZnszjClientConstants:
    def test_urls(self) -> None:
        assert GDZQFY_URL == "https://www.gdzqfy.gov.cn/api/utils/getscwsurl"
        assert ZNSZJ_BASE == "https://wxfxpg.susong51.com/znszj-touch"
        assert TIMEOUT == 60


class TestZnszjClientAuthenticate:
    def test_authenticate_success(self) -> None:
        """Happy path: all three auth steps succeed."""
        client = ZnszjClient()

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"code": "200", "data": "https://example.com?signatureCode=ABC123"}
        mock_resp1.raise_for_status = MagicMock()

        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"success": True, "data": {"token": "tok", "mac": "mac123"}}
        mock_resp2.raise_for_status = MagicMock()

        mock_resp3 = MagicMock()
        mock_resp3.json.return_value = {"success": True, "code": "sbbs456"}
        mock_resp3.raise_for_status = MagicMock()

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.post.side_effect = [mock_resp1, mock_resp2, mock_resp3]
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            result = client._authenticate()
        assert result["token"] == "tok"
        assert result["mac"] == "mac123"
        assert result["sbbs"] == "sbbs456"

    def test_authenticate_step1_failure(self) -> None:
        """Step 1 (getscwsurl) returns non-200 code."""
        client = ZnszjClient()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": "500", "message": "server error"}
        mock_resp.raise_for_status = MagicMock()

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with pytest.raises(ZnszjUnavailableError):
                client._authenticate()

    def test_authenticate_step2_failure(self) -> None:
        """Step 2 (authentication) returns success=False."""
        client = ZnszjClient()
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"code": "200", "data": "https://example.com?signatureCode=ABC123"}
        mock_resp1.raise_for_status = MagicMock()

        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"success": False, "message": "invalid code"}
        mock_resp2.raise_for_status = MagicMock()

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.post.side_effect = [mock_resp1, mock_resp2]
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with pytest.raises(ZnszjUnavailableError):
                client._authenticate()


class TestZnszjClientConvertDocument:
    def test_convert_document_auth_failure_wraps_error(self) -> None:
        """Authentication failure wraps into ZnszjUnavailableError."""
        client = ZnszjClient()
        with patch.object(client, "_authenticate", side_effect=RuntimeError("network")):
            with pytest.raises(ZnszjUnavailableError):
                client.convert_document(file_content=b"data", filename="test.docx", mbid="MB001")

    def test_convert_document_success(self) -> None:
        """Happy path: full conversion flow."""
        client = ZnszjClient()

        auth_result = {"token": "tok", "mac": "mac", "sbbs": "sbbs"}

        with (
            patch.object(client, "_authenticate", return_value=auth_result),
            patch.object(client, "_run_conversion", return_value=b"docx-content"),
        ):
            result = client.convert_document(file_content=b"input", filename="file.docx", mbid="MB001")
        assert result == b"docx-content"

    def test_convert_document_conversion_failure(self) -> None:
        """Conversion step failure wraps correctly."""
        client = ZnszjClient()
        auth_result = {"token": "tok", "mac": "mac", "sbbs": "sbbs"}

        with (
            patch.object(client, "_authenticate", return_value=auth_result),
            patch.object(client, "_run_conversion", side_effect=ZnszjInvalidResponseError(detail="bad")),
        ):
            with pytest.raises(ZnszjInvalidResponseError):
                client.convert_document(file_content=b"input", filename="file.docx", mbid="MB001")
