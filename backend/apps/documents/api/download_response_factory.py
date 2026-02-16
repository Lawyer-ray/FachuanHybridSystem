"""API endpoints."""

from urllib.parse import quote

from django.http import HttpResponse


def build_download_response(*, content: bytes, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response
