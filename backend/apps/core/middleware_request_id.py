"""Module for middleware request id."""

from __future__ import annotations

import contextlib
import logging
import re
import threading
from collections.abc import Callable
from typing import Any, cast

from django.http import HttpRequest, HttpResponse

from apps.core.infrastructure.request_context import clear_request_context, generate_request_id, set_request_context
from apps.core.infrastructure.tracing import get_current_trace_ids

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        candidate = request.headers.get("X-Request-ID") or ""
        candidate = str(candidate).strip()
        if candidate and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate):
            request_id = candidate
        else:
            request_id = generate_request_id()
        trace_id, span_id = get_current_trace_ids()

        set_request_context(
            request_id=request_id,
            trace_id=trace_id or request_id,
            span_id=span_id,
        )
        cast(Any, request).request_id = request_id
        thread = cast(Any, threading.current_thread())
        thread.request_id = request_id
        thread.trace_id = trace_id or request_id

        try:
            response = self.get_response(request)
            try:
                response.headers["X-Request-ID"] = request_id
            except (AttributeError, TypeError, KeyError):
                with contextlib.suppress(Exception):
                    response["X-Request-ID"] = request_id
            return response
        finally:
            clear_request_context()
            for attr in ("request_id", "trace_id"):
                if hasattr(threading.current_thread(), attr):
                    with contextlib.suppress(Exception):
                        delattr(threading.current_thread(), attr)
