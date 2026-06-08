"""测试 HTTP 流式响应构建

覆盖: apps/core/http/streaming.py
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from django.http import HttpRequest


@pytest.fixture
def temp_file() -> str:
    """创建一个临时文件用于测试"""
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, b"Hello, World! This is a test file.")
    os.close(fd)
    yield path
    os.unlink(path)


def _make_request(method: str = "GET", range_header: str = "") -> HttpRequest:
    request = MagicMock(spec=HttpRequest)
    request.method = method
    request.headers = {"Range": range_header} if range_header else {}
    request.META = {}
    return request


class TestBuildRangeFileResponse:
    """测试 build_range_file_response"""

    def test_file_not_found(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, "/nonexistent/file.txt")
        assert response.status_code == 404

    def test_empty_file_path(self) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, "")
        assert response.status_code == 404

    def test_full_file_response(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 200
        assert response.get("Accept-Ranges") == "bytes"
        assert response.get("Content-Length") == str(os.path.getsize(temp_file))

    def test_head_request(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request(method="HEAD")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 200
        assert response.get("Accept-Ranges") == "bytes"
        assert response.get("Content-Length") == str(os.path.getsize(temp_file))

    def test_range_request(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request(range_header="bytes=0-4")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 206
        assert response.get("Accept-Ranges") == "bytes"
        assert response.get("Content-Length") == "5"
        assert "bytes 0-4/" in response.get("Content-Range", "")

    def test_range_head_request(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request(method="HEAD", range_header="bytes=0-4")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 206
        assert response.get("Content-Length") == "5"

    def test_range_beyond_file_size(self, temp_file: str) -> None:
        """请求范围超过文件大小时，_parse_explicit_range 会将 start/end 限制在 file_size-1"""
        from apps.core.http.streaming import build_range_file_response

        file_size = os.path.getsize(temp_file)
        request = _make_request(range_header=f"bytes={file_size + 100}-{file_size + 200}")
        response = build_range_file_response(request, temp_file)
        # The range parser caps start/end to file_size-1, so this returns 206 not 416
        assert response.status_code == 206

    def test_custom_content_type(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, content_type="text/html")
        assert response.get("Content-Type") == "text/html"
