"""Tests for apps.core.http.httpx_clients and apps.core.http.streaming."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from apps.core.http.httpx_clients import _httpx_event_hooks


class TestHttpxEventHooks:
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": ""}, clear=False):
            result = _httpx_event_hooks()
            assert result is None

    def test_enabled(self):
        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "true"}, clear=False):
            result = _httpx_event_hooks()
            assert result is not None
            assert "request" in result
            assert "response" in result

    def test_on_request_sets_metrics(self):
        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "1"}, clear=False):
            hooks = _httpx_event_hooks()
            request = MagicMock()
            request.extensions = {}
            hooks["request"][0](request)
            assert "metrics_started_at" in request.extensions

    def test_on_response_records_metrics(self):
        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "yes"}, clear=False):
            with patch("apps.core.http.httpx_clients.time") as mock_time:
                mock_time.perf_counter.return_value = 100.0
                hooks = _httpx_event_hooks()
                response = MagicMock()
                response.request.extensions = {"metrics_started_at": 99.0}
                response.request.url.host = "example.com"
                response.request.method = "GET"
                response.status_code = 200
                with patch("apps.core.telemetry.metrics.record_httpx") as mock_record:
                    hooks["response"][0](response)
                    mock_record.assert_called_once()

    def test_on_response_no_started_at(self):
        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "true"}, clear=False):
            hooks = _httpx_event_hooks()
            response = MagicMock()
            response.request.extensions = {}
            hooks["response"][0](response)  # Should not raise


class TestBuildRangeFileResponse:
    def test_missing_file(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test")
        resp = build_range_file_response(request, "/nonexistent/file.pdf")
        assert resp.status_code == 404

    def test_empty_path(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test")
        resp = build_range_file_response(request, "")
        assert resp.status_code == 404

    def test_full_request(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 200
                assert resp["Accept-Ranges"] == "bytes"
            finally:
                os.unlink(f.name)

    def test_head_request(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.head("/test")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 200
                assert resp["Content-Length"] == "5"
            finally:
                os.unlink(f.name)

    def test_range_request(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test", HTTP_RANGE="bytes=0-4")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 206
                assert resp["Content-Range"] == "bytes 0-4/11"
            finally:
                os.unlink(f.name)

    def test_range_start_beyond_file(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test", HTTP_RANGE="bytes=100-200")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hi")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 416
            finally:
                os.unlink(f.name)

    def test_invalid_range_header(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test", HTTP_RANGE="bytes=")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 416
            finally:
                os.unlink(f.name)

    def test_head_request_with_range(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.head("/test", HTTP_RANGE="bytes=0-4")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name)
                assert resp.status_code == 206
            finally:
                os.unlink(f.name)

    def test_as_attachment(self):
        from django.test import RequestFactory
        from apps.core.http.streaming import build_range_file_response
        factory = RequestFactory()
        request = factory.get("/test")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"content")
            f.flush()
            try:
                resp = build_range_file_response(request, f.name, as_attachment=True)
                assert "Content-Disposition" in resp
                assert "attachment" in resp["Content-Disposition"]
            finally:
                os.unlink(f.name)
