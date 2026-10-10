"""Tests for plugins.doc_convert.znszj_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

pytest.importorskip("plugins.doc_convert", reason="doc_convert plugin not installed")

from apps.doc_convert.exceptions import ZnszjInvalidResponseError, ZnszjUnavailableError
from plugins.doc_convert.znszj_client import GDZQFY_URL, MAX_ATTEMPTS, TIMEOUT, ZNSZJ_BASE, ZnszjClient, _make_client


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
    @staticmethod
    def _ok_resp(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        return resp

    def test_authenticate_success(self) -> None:
        """Happy path: all three auth steps succeed."""
        client = ZnszjClient()

        mock_resp1 = self._ok_resp({"code": "200", "data": "https://example.com?signatureCode=ABC123"})
        mock_resp2 = self._ok_resp({"success": True, "data": {"token": "tok", "mac": "mac123"}})
        mock_resp3 = self._ok_resp({"success": True, "code": "sbbs456"})

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.side_effect = [mock_resp1, mock_resp2, mock_resp3]
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
        mock_resp = self._ok_resp({"code": "500", "message": "server error"})

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.return_value = mock_resp
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with pytest.raises(ZnszjUnavailableError):
                client._authenticate()

    def test_authenticate_step2_failure(self) -> None:
        """Step 2 (authentication) returns success=False."""
        client = ZnszjClient()
        mock_resp1 = self._ok_resp({"code": "200", "data": "https://example.com?signatureCode=ABC123"})
        mock_resp2 = self._ok_resp({"success": False, "message": "invalid code"})

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.side_effect = [mock_resp1, mock_resp2]
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with pytest.raises(ZnszjUnavailableError):
                client._authenticate()

    def test_authenticate_missing_signature_code(self) -> None:
        """Step 1 返回链接不含 signatureCode → ZnszjInvalidResponseError（远端改格式时的防护）。"""
        client = ZnszjClient()
        mock_resp1 = self._ok_resp({"code": "200", "data": "https://example.com/other"})

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.return_value = mock_resp1
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with pytest.raises(ZnszjInvalidResponseError):
                client._authenticate()


class TestZnszjClientRetry:
    """瞬时网络错误自动重试。"""

    @staticmethod
    def _auth_mocks() -> tuple[MagicMock, MagicMock, MagicMock]:
        """构造三步认证的正常应答 mock。"""
        r1 = MagicMock()
        r1.json.return_value = {"code": "200", "data": "https://example.com?signatureCode=ABC123"}
        r1.raise_for_status = MagicMock()
        r2 = MagicMock()
        r2.json.return_value = {"success": True, "data": {"token": "tok", "mac": "mac123"}}
        r2.raise_for_status = MagicMock()
        r3 = MagicMock()
        r3.json.return_value = {"success": True, "code": "sbbs456"}
        r3.raise_for_status = MagicMock()
        return r1, r2, r3

    def test_transient_error_retried_then_success(self) -> None:
        """第一步瞬时断连：自动重试后认证成功，不抛异常。"""
        client = ZnszjClient()
        r1, r2, r3 = self._auth_mocks()

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.side_effect = [
                httpx.RemoteProtocolError("Server disconnected without sending a response."),
                r1,
                r2,
                r3,
            ]
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with patch("plugins.doc_convert.znszj_client.time.sleep") as mock_sleep:
                result = client._authenticate()

        assert result["sbbs"] == "sbbs456"
        mock_sleep.assert_called_once()

    def test_retry_exhausted_raises_with_step(self) -> None:
        """持续断连：重试耗尽后抛 ZnszjUnavailableError，带 step 与 detail。"""
        client = ZnszjClient()

        with patch("plugins.doc_convert.znszj_client._make_client") as mock_factory:
            mock_http = MagicMock()
            mock_http.request.side_effect = httpx.ConnectError("connection refused")
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_http

            with patch("plugins.doc_convert.znszj_client.time.sleep"):
                with pytest.raises(ZnszjUnavailableError) as exc_info:
                    client._authenticate()

        assert mock_http.request.call_count == MAX_ATTEMPTS
        assert exc_info.value.errors.get("step")
        assert "ConnectError" in (exc_info.value.errors.get("detail") or "")
        assert "请稍后重试" in str(exc_info.value.message)


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
