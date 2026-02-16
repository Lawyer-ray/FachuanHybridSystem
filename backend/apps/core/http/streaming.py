"""Module for streaming."""

from __future__ import annotations

import mimetypes
import os
from collections.abc import Iterator

from django.http import HttpRequest, HttpResponse, HttpResponseBase


def build_range_file_response(
    request: HttpRequest,
    file_path: str,
    *,
    content_type: str | None = None,
    chunk_size: int = 1024 * 512,
) -> HttpResponseBase:
    from django.http import FileResponse, StreamingHttpResponse

    from .range import parse_range_header

    if not file_path or not os.path.exists(file_path):
        return HttpResponse(status=404)

    file_size = os.path.getsize(file_path)
    guessed, _ = mimetypes.guess_type(file_path)
    ct: str = content_type or guessed or "application/octet-stream"

    range_header: str = request.headers.get("Range") or request.META.get("HTTP_RANGE", "") or ""
    byte_range = parse_range_header(range_header, file_size)
    if not byte_range:
        if request.method == "HEAD":
            head_resp = HttpResponse(content_type=ct)
            head_resp["Accept-Ranges"] = "bytes"
            head_resp["Content-Length"] = str(file_size)
            return head_resp
        file_resp = FileResponse(open(file_path, "rb"), content_type=ct)
        file_resp["Accept-Ranges"] = "bytes"
        file_resp["Content-Length"] = str(file_size)
        return file_resp

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
        return resp

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
    return stream_resp
