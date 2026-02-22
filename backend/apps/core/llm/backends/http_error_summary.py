"""Module for http error summary."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def summarize_http_error_response(
    response: httpx.Response,
    *,
    max_text_len: int = 200,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"status_code": response.status_code}

    request_id = (
        response.headers.get("x-request-id")
        or response.headers.get("x-trace-id")
        or response.headers.get("x-amzn-requestid")
        or response.headers.get("request-id")
    )
    if request_id:
        summary["upstream_request_id"] = request_id

    content_type = response.headers.get("content-type")
    if content_type:
        summary["content_type"] = content_type

    error_message: str | None = None
    error_code: str | None = None

    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                error_message = _first_str(err, ["message", "detail", "error", "msg"])
                error_code = _first_str(err, ["code", "type"])
            elif isinstance(err, str):
                error_message = err
            else:
                error_message = _first_str(data, ["message", "detail", "error"])

            if error_code:
                summary["upstream_error_code"] = _truncate(error_code, max_text_len)
            if error_message:
                summary["upstream_error_message"] = _truncate(error_message, max_text_len)
            return summary
    except (ValueError, KeyError, AttributeError):
        pass

    text = (response.text or "").strip()
    if text:
        summary["upstream_error_text"] = _truncate(text, max_text_len)
    return summary


def _first_str(data: dict[str, Any], keys: list[str]) -> str | None:
    for k in keys:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."
