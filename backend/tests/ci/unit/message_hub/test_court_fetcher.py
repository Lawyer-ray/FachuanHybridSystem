"""Court fetcher tests with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_message_hub_plugin
    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")

if _HAS_MH:
    from plugins.message_hub.services.court.court_fetcher import (
        CourtInboxFetcher,
        _api_post,
        _build_body,
        _build_subject,
        _parse_datetime,
        _run_callable_with_timeout,

)

class TestBuildSubject:
    def test_build_subject_with_ah(self):
        record = {"ah": "2024京123号", "wsmc": "判决书"}
        assert _build_subject(record) == "2024京123号 - 判决书"

    def test_build_subject_no_ah(self):
        record = {"ah": "", "wsmc": "判决书"}
        assert _build_subject(record) == "判决书"

    def test_build_subject_empty(self):
        assert _build_subject({}) == "(无主题)"

class TestBuildBody:
    def test_build_body(self):
        record = {"ah": "2024京123", "fymc": "朝阳法院", "wsmc": "判决书", "fqr": "张三", "sdzt": "已送达", "qdzt": "已签收", "fssj": "2024-01-01 12:00:00"}
        body = _build_body(record)
        assert "2024京123" in body
        assert "朝阳法院" in body

class TestParseDatetime:
    def test_parse_datetime_valid(self):
        dt = _parse_datetime("2024-01-15 10:30:00")
        assert dt.year == 2024
        assert dt.month == 1

    def test_parse_datetime_invalid(self):
        import django.utils.timezone as tz

        dt = _parse_datetime("invalid")
        # Should return timezone.now() as fallback
        assert dt is not None

class TestRunWithCallableTimeout:
    def test_success(self):
        result = _run_callable_with_timeout(lambda: "ok", timeout_seconds=5)
        assert result == "ok"

    def test_timeout(self):
        import time

        def slow():
            time.sleep(10)
            return "late"

        with pytest.raises(TimeoutError):
            _run_callable_with_timeout(slow, timeout_seconds=0.1)

    def test_exception(self):
        def fail():
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            _run_callable_with_timeout(fail, timeout_seconds=5)

class TestApiPost:
    @patch("plugins.message_hub.services.court.court_fetcher.httpx.Client")
    def test_api_post_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 200, "data": {"items": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = _api_post("https://example.com/api", "token123", {"pageNum": 1})
        assert result["code"] == 200

    @patch("plugins.message_hub.services.court.court_fetcher.httpx.Client")
    def test_api_post_unauthorized(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(PermissionError):
            _api_post("https://example.com/api", "expired", {})

class TestCourtInboxFetcher:
    def test_fetcher_class_exists(self):
        fetcher = CourtInboxFetcher()
        assert hasattr(fetcher, "fetch_new_messages")
        assert hasattr(fetcher, "download_attachment")
