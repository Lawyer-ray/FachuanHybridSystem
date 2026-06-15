"""Comprehensive unit tests for mcp_server.client.FachuanClient"""

from __future__ import annotations

import json as _json
import time
from unittest import mock

import httpx
import pytest

# Patch config values BEFORE importing client so module-level constants are
# picked up correctly.  We only need valid-looking values so FachuanClient()
# can be instantiated without errors.
with mock.patch.dict(
    "os.environ",
    {
        "FACHUAN_BASE_URL": "http://testserver/api/v1",
        "FACHUAN_USERNAME": "testuser",
        "FACHUAN_PASSWORD": "testpass",
    },
    clear=False,
):
    from mcp_server import client as client_mod
    from mcp_server.client import FachuanClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_BASE = "http://testserver/api/v1"


def _make_response(
    status_code: int = 200,
    json_data: object | None = None,
    text: str = "",
    content: bytes = b"",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build an httpx.Response without going over the wire."""
    headers = headers or {}
    # If json_data is provided, serialize it into content bytes so
    # resp.json() and resp.content both work correctly.
    if json_data is not None:
        content = _json.dumps(json_data).encode("utf-8")
        headers.setdefault("content-type", "application/json")
    elif text and not content:
        content = text.encode("utf-8")
    resp = httpx.Response(
        status_code=status_code,
        headers=headers,
        content=content,
        request=httpx.Request("GET", REAL_BASE),
    )
    return resp


def _patch_http(monkeypatch: pytest.MonkeyPatch):
    """Replace the internal httpx.Client on a fresh FachuanClient."""
    fake_http = mock.MagicMock(spec=httpx.Client)
    fake_http.base_url = REAL_BASE
    return fake_http


@pytest.fixture()
def fc(monkeypatch: pytest.MonkeyPatch) -> tuple[FachuanClient, mock.MagicMock]:
    """Create a FachuanClient with a mocked httpx.Client and valid tokens."""
    c = FachuanClient()
    fake_http = mock.MagicMock(spec=httpx.Client)
    fake_http.base_url = REAL_BASE
    c._http = fake_http
    # Pre-load a valid token so _ensure_token short-circuits.
    c._access_token = "access-xyz"
    c._refresh_token = "refresh-abc"
    c._expires_at = time.time() + 9999
    return c, fake_http


# ===================================================================
# 1. Token acquisition (_obtain_token)
# ===================================================================


class TestObtainToken:
    """Tests for _obtain_token retry + success logic."""

    def test_obtain_token_success_first_try(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.post.return_value = _make_response(
            200, json_data={"access": "new-access", "refresh": "new-refresh"}
        )
        c._access_token = ""
        c._obtain_token()

        assert c._access_token == "new-access"
        assert c._refresh_token == "new-refresh"
        assert c._expires_at > time.time()
        http.post.assert_called_once_with(
            "/token/pair",
            json={"username": "testuser", "password": "testpass"},
        )

    def test_obtain_token_retries_on_500_then_succeeds(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        fail_resp = _make_response(500, text="oops")
        ok_resp = _make_response(200, json_data={"access": "a", "refresh": "r"})
        http.post.side_effect = [
            httpx.HTTPStatusError("err", request=fail_resp.request, response=fail_resp),
            ok_resp,
        ]
        c._access_token = ""

        with mock.patch.object(client_mod.time, "sleep") as sleep_mock:
            c._obtain_token()

        assert c._access_token == "a"
        assert http.post.call_count == 2
        sleep_mock.assert_called_once_with(1.0)  # first backoff

    def test_obtain_token_retries_on_connect_error(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        ok_resp = _make_response(200, json_data={"access": "a2", "refresh": "r2"})
        http.post.side_effect = [
            httpx.ConnectError("refused"),
            ok_resp,
        ]
        c._access_token = ""

        with mock.patch.object(client_mod.time, "sleep") as sleep_mock:
            c._obtain_token()

        assert c._access_token == "a2"
        assert http.post.call_count == 2
        sleep_mock.assert_called_once_with(1.0)

    def test_obtain_token_exhausts_retries_raises(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.post.side_effect = httpx.ConnectError("down")
        c._access_token = ""

        with mock.patch.object(client_mod.time, "sleep"):
            with pytest.raises(httpx.ConnectError):
                c._obtain_token()

        assert http.post.call_count == 3  # _MAX_OBTAIN_RETRIES

    def test_obtain_token_4xx_raises_immediately(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        fail_resp = _make_response(401, text="unauthorized")
        http.post.side_effect = httpx.HTTPStatusError(
            "401", request=fail_resp.request, response=fail_resp
        )
        c._access_token = ""

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            c._obtain_token()

        assert exc_info.value.response.status_code == 401
        assert http.post.call_count == 1  # no retry for 4xx

    def test_obtain_token_uses_correct_backoff_sequence(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.post.side_effect = httpx.ConnectError("down")
        c._access_token = ""

        sleep_calls: list[float] = []
        with mock.patch.object(
            client_mod.time, "sleep", side_effect=lambda t: sleep_calls.append(t)
        ):
            with pytest.raises(httpx.ConnectError):
                c._obtain_token()

        # Should sleep twice: before attempt 2 and attempt 3
        assert sleep_calls == [1.0, 3.0]


# ===================================================================
# 2. Token refresh (_refresh)
# ===================================================================


class TestRefreshToken:
    """Tests for _refresh behaviour."""

    def test_refresh_success(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        c._refresh_token = "old-refresh"
        http.post.return_value = _make_response(
            200, json_data={"access": "refreshed-access"}
        )

        c._refresh()

        assert c._access_token == "refreshed-access"
        http.post.assert_called_once_with(
            "/token/refresh", json={"refresh": "old-refresh"}
        )

    def test_refresh_failure_falls_back_to_obtain(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        # First call (refresh) fails; second call (obtain) succeeds.
        fail_resp = _make_response(401)
        obtain_resp = _make_response(
            200, json_data={"access": "fresh", "refresh": "fresh-r"}
        )
        http.post.side_effect = [
            httpx.HTTPStatusError("401", request=fail_resp.request, response=fail_resp),
            obtain_resp,
        ]
        c._access_token = "expired"
        c._expires_at = 0

        c._ensure_token()

        assert c._access_token == "fresh"
        assert c._refresh_token == "fresh-r"


# ===================================================================
# 3. _ensure_token logic
# ===================================================================


class TestEnsureToken:
    """Tests for _ensure_token routing."""

    def test_obtains_when_no_access_token(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        c._access_token = ""
        http.post.return_value = _make_response(
            200, json_data={"access": "a", "refresh": "r"}
        )
        c._ensure_token()
        assert c._access_token == "a"

    def test_refreshes_when_expired(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        c._expires_at = time.time() - 100
        http.post.return_value = _make_response(
            200, json_data={"access": "renewed"}
        )
        c._ensure_token()
        assert c._access_token == "renewed"

    def test_skips_when_token_valid(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        c._access_token = "still-good"
        c._expires_at = time.time() + 9999
        c._ensure_token()
        http.post.assert_not_called()


# ===================================================================
# 4. HTTP method wrappers
# ===================================================================


class TestHTTPMethods:
    """Tests for get, post, put, delete wrappers."""

    def test_get_success(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.get.return_value = _make_response(200, json_data={"id": 1})
        result = c.get("/items")
        assert result == {"id": 1}
        http.get.assert_called_once()
        call_kwargs = http.get.call_args
        assert "/items" in call_kwargs[0]
        assert "Authorization" in call_kwargs[1]["headers"]

    def test_post_success(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.post.return_value = _make_response(201, json_data={"id": 42})
        result = c.post("/items", json={"name": "foo"})
        assert result == {"id": 42}

    def test_put_success(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.put.return_value = _make_response(200, json_data={"updated": True})
        result = c.put("/items/1", json={"name": "bar"})
        assert result == {"updated": True}

    def test_delete_success_returns_none(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.delete.return_value = _make_response(204)
        result = c.delete("/items/1")
        assert result is None

    def test_delete_success_returns_json(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.delete.return_value = _make_response(200, json_data={"deleted": True})
        result = c.delete("/items/1")
        assert result == {"deleted": True}

    def test_headers_include_bearer_token(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        c._access_token = "my-token"
        http.get.return_value = _make_response(200, json_data={})
        c.get("/anything")
        sent_headers = http.get.call_args[1]["headers"]
        assert sent_headers["Authorization"] == "Bearer my-token"


# ===================================================================
# 5. Error handling (_handle)
# ===================================================================


class TestHandleError:
    """Tests for _handle static method and error paths in HTTP methods."""

    def test_400_raises_runtime_error_with_json_detail(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.get.return_value = _make_response(400, json_data={"detail": "bad input"})
        with pytest.raises(RuntimeError, match=r"HTTP 400.*bad input"):
            c.get("/items")

    def test_500_raises_runtime_error_with_text_fallback(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        # Build a response where .json() will raise to test the fallback path
        resp = _make_response(500, text="Internal Server Error", content=b"Internal Server Error")
        resp_without_json = httpx.Response(
            status_code=500,
            content=b"Internal Server Error",
            request=httpx.Request("GET", REAL_BASE),
        )
        http.get.return_value = resp_without_json
        with pytest.raises(RuntimeError, match=r"HTTP 500.*Internal Server Error"):
            c.get("/items")

    def test_204_returns_none(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.delete.return_value = _make_response(204)
        assert c.delete("/items/1") is None

    def test_200_returns_json(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, http = fc
        http.get.return_value = _make_response(200, json_data={"ok": True})
        assert c.get("/ping") == {"ok": True}


class TestDownloadError:
    """Download method error paths."""

    def test_download_non_success_raises_runtime_error(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        resp = _make_response(404, json_data={"detail": "not found"})
        http.get.return_value = resp
        with pytest.raises(RuntimeError, match=r"HTTP 404"):
            c.download("/files/missing")


# ===================================================================
# 6. Upload (multipart/form-data)
# ===================================================================


class TestUpload:
    """Tests for the upload method."""

    def test_upload_sends_multipart_with_files_and_data(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.post.return_value = _make_response(200, json_data={"uploaded": True})
        files = {"file": ("test.txt", b"hello", "text/plain")}
        data = {"description": "a file"}

        result = c.upload("/upload", files=files, data=data)

        assert result == {"uploaded": True}
        http.post.assert_called_once()
        call_args = http.post.call_args
        assert call_args[1]["files"] is files
        assert call_args[1]["data"] == data
        assert "Authorization" in call_args[1]["headers"]

    def test_upload_without_data_defaults_to_empty_dict(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.post.return_value = _make_response(200, json_data={"ok": True})
        files = {"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}

        c.upload("/upload", files=files)

        call_args = http.post.call_args
        assert call_args[1]["data"] == {}


# ===================================================================
# 7. Download (Content-Disposition parsing)
# ===================================================================


class TestDownload:
    """Tests for the download method's response parsing."""

    def _make_download_response(
        self,
        content: bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        hdrs = headers or {}
        return httpx.Response(
            status_code=status,
            headers=hdrs,
            content=content,
            request=httpx.Request("GET", REAL_BASE),
        )

    def test_download_returns_content_and_defaults(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        body = b"\x89PNG\r\n"
        http.get.return_value = self._make_download_response(body)

        data, fname, ctype = c.download("/files/img.png")

        assert data == body
        assert fname == "download"  # fallback when no Content-Disposition
        assert ctype == "application/octet-stream"  # fallback

    def test_download_parses_filename_star_utf8(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        from urllib.parse import quote

        encoded_name = quote("测试文件.pdf")
        disposition = f"attachment; filename*=UTF-8''{encoded_name}"
        http.get.return_value = self._make_download_response(
            b"%PDF", headers={"content-disposition": disposition, "content-type": "application/pdf"}
        )

        data, fname, ctype = c.download("/files/doc.pdf")

        assert fname == "测试文件.pdf"
        assert ctype == "application/pdf"

    def test_download_parses_filename_quoted(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.get.return_value = self._make_download_response(
            b"data",
            headers={"content-disposition": 'attachment; filename="report.xlsx"'},
        )

        _, fname, _ = c.download("/files/report")

        assert fname == "report.xlsx"

    def test_download_parses_filename_unquoted(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.get.return_value = self._make_download_response(
            b"data",
            headers={"content-disposition": "attachment; filename=report.xlsx"},
        )

        _, fname, _ = c.download("/files/report")

        assert fname == "report.xlsx"

    def test_download_prefers_filename_star_over_filename(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        from urllib.parse import quote

        encoded = quote("中文.xlsx")
        disposition = f'attachment; filename="fallback.xlsx"; filename*=UTF-8\'\'{encoded}'
        http.get.return_value = self._make_download_response(
            b"data", headers={"content-disposition": disposition}
        )

        _, fname, _ = c.download("/files/x")

        assert fname == "中文.xlsx"

    def test_download_raises_on_error_status(
        self, fc: tuple[FachuanClient, mock.MagicMock]
    ):
        c, http = fc
        http.get.return_value = httpx.Response(
            status_code=500,
            content=b"Server Error",
            request=httpx.Request("GET", REAL_BASE),
        )
        with pytest.raises(RuntimeError, match=r"HTTP 500"):
            c.download("/files/bad")


# ===================================================================
# 8. _headers helper
# ===================================================================


class TestHeaders:
    """Tests for _headers returning Authorization with Bearer token."""

    def test_headers_returns_bearer(self, fc: tuple[FachuanClient, mock.MagicMock]):
        c, _ = fc
        c._access_token = "tok123"
        h = c._headers()
        assert h == {"Authorization": "Bearer tok123"}


# ===================================================================
# 9. _handle static method edge cases
# ===================================================================


class TestHandleStatic:
    """Tests for the static _handle method directly."""

    def test_handle_json_parse_error_falls_back_to_text(self):
        resp = httpx.Response(
            status_code=422,
            content=b"not json",
            request=httpx.Request("POST", REAL_BASE),
        )
        with pytest.raises(RuntimeError, match=r"HTTP 422.*not json"):
            FachuanClient._handle(resp)

    def test_handle_204_returns_none(self):
        resp = _make_response(204)
        assert FachuanClient._handle(resp) is None

    def test_handle_200_returns_json(self):
        resp = _make_response(200, json_data={"key": "val"})
        assert FachuanClient._handle(resp) == {"key": "val"}
