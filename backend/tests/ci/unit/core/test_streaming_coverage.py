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
        """请求范围超过文件大小时，应返回 416 Range Not Satisfiable"""
        from apps.core.http.streaming import build_range_file_response

        file_size = os.path.getsize(temp_file)
        request = _make_request(range_header=f"bytes={file_size + 100}-{file_size + 200}")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 416

    def test_custom_content_type(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, content_type="application/json")
        assert response.get("Content-Type") == "application/json"

    def test_as_attachment_sets_disposition(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, as_attachment=True)
        assert "attachment" in response.get("Content-Disposition", "")

    def test_dangerous_content_type_forced_to_octet(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, content_type="text/html")
        assert response.get("X-Content-Type-Options") == "nosniff"

    def test_svg_content_type_forced_download(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, content_type="image/svg+xml")
        assert response.get("X-Content-Type-Options") == "nosniff"

    def test_x_content_type_options_always_set(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file)
        assert response.get("X-Content-Type-Options") == "nosniff"

    def test_range_streaming_response_content(self, tmp_path) -> None:
        from apps.core.http.streaming import build_range_file_response

        p = tmp_path / "big.bin"
        p.write_bytes(b"X" * 1024 * 1024)  # 1MB
        request = _make_request(range_header="bytes=0-511")
        response = build_range_file_response(request, str(p), chunk_size=256)
        assert response.status_code == 206
        assert response["Content-Length"] == "512"

    def test_invalid_range_returns_416(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request(range_header="bytes=500-100")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 416

    def test_attachment_sets_filename(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request()
        response = build_range_file_response(request, temp_file, as_attachment=True, content_type="application/octet-stream")
        assert 'filename="' in response.get("Content-Disposition", "")

    def test_no_range_head_request(self, temp_file: str) -> None:
        from apps.core.http.streaming import build_range_file_response

        request = _make_request(method="HEAD")
        response = build_range_file_response(request, temp_file)
        assert response.status_code == 200
        assert response["Accept-Ranges"] == "bytes"
