"""API endpoints."""

from __future__ import annotations

from django.http import HttpResponse

from apps.core.http.download import build_download_response as _core_build_download_response

__all__ = ["build_download_response"]


def build_download_response(*, content: bytes, filename: str, content_type: str) -> HttpResponse:
    """解耦（2026-10-19）：委托 ``core/http/download`` 的统一实现（本函数签名保持不变，调用方零改动）。"""
    return _core_build_download_response(content, filename, content_type)
