"""Module for streaming."""

from __future__ import annotations

import mimetypes
import os
from collections.abc import Iterator

from django.http import HttpRequest, HttpResponse, HttpResponseBase

# 危险的 Content-Type，可能导致 XSS（浏览器会渲染/执行）
_DANGEROUS_CONTENT_TYPES = frozenset({
    "text/html",
    "text/xml",
    "application/xhtml+xml",
    "image/svg+xml",
    "application/xml",
    "application/javascript",
    "text/javascript",
})


def build_range_file_response(
    request: HttpRequest,
    file_path: str,
    *,
    content_type: str | None = None,
    chunk_size: int = 1024 * 512,
    as_attachment: bool = False,
) -> HttpResponseBase:
    from django.http import FileResponse, StreamingHttpResponse

    from .range import parse_range_header

    if not file_path or not os.path.exists(file_path):
        return HttpResponse(status=404)

    file_size = os.path.getsize(file_path)
    guessed, _ = mimetypes.guess_type(file_path)
    ct: str = content_type or guessed or "application/octet-stream"

    # 安全加固：对危险 Content-Type 强制下载，防止 XSS
    if ct in _DANGEROUS_CONTENT_TYPES:
        ct = "application/octet-stream"
        as_attachment = True

    range_header: str = request.headers.get("Range") or request.META.get("HTTP_RANGE", "") or ""
    byte_range = parse_range_header(range_header, file_size)

    # 如果 Range 请求头存在但解析失败或范围无效，返回 416 Range Not Satisfiable (RFC 7233)
    if range_header and not byte_range:
        resp = HttpResponse(status=416)
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Range"] = f"bytes */{file_size}"
        return resp

    def _set_security_headers(resp: HttpResponseBase) -> HttpResponseBase:
        resp["X-Content-Type-Options"] = "nosniff"
        if as_attachment:
            filename = os.path.basename(file_path)
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    if not byte_range:
        if request.method == "HEAD":
            head_resp = HttpResponse(content_type=ct)
            head_resp["Accept-Ranges"] = "bytes"
            head_resp["Content-Length"] = str(file_size)
            return _set_security_headers(head_resp)
        file_resp = FileResponse(open(file_path, "rb"), content_type=ct)
        file_resp["Accept-Ranges"] = "bytes"
        file_resp["Content-Length"] = str(file_size)
        return _set_security_headers(file_resp)

    start, end = byte_range
    if start >= file_size:
        resp = HttpResponse(status=416)
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Range"] = f"bytes */{file_size}"
        return resp

    length = end - start + 1
    if request.method == "HEAD":
        resp = HttpResponse(status=206, content_type=ct)
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Length"] = str(length)
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return _set_security_headers(resp)

    def _iter_file(path: str, start_pos: int, count: int) -> Iterator[bytes]:
        with open(path, "rb") as f:
            f.seek(start_pos)
            remaining = count
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    stream_resp = StreamingHttpResponse(_iter_file(file_path, start, length), status=206, content_type=ct)
    stream_resp["Accept-Ranges"] = "bytes"
    stream_resp["Content-Length"] = str(length)
    stream_resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return _set_security_headers(stream_resp)
