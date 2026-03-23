"""API endpoints."""

from urllib.parse import quote

from django.http import HttpResponse


def build_download_response(*, content: bytes, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    # filename="..." 使用百分号编码（ASCII 安全，避免 Django MIME 编码破坏正则匹配）
    # filename*=UTF-8'' 同样使用百分号编码（RFC 5987，浏览器会自动解码）
    response["Content-Disposition"] = (
        f"attachment; filename=\"{quote(filename)}\"; filename*=UTF-8''{quote(filename)}"
    )
    return response
