"""Module for middleware request id."""

from __future__ import annotations

import asyncio
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
    """双模中间件：sync 链直接执行，async 链返回协程由 Django handler await。

    不设置 async_capable=True，让 Django 用 sync_to_async 包装本中间件。
    __call__ 在线程中运行，async 路径返回协程由 Django handler await。
    """

    _is_async: bool
    get_response: Callable[..., Any]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._is_async = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request: HttpRequest) -> Any:
        request_id = self._extract_request_id(request)
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

        # async 链：get_response 是协程函数，返回协程让 Django handler await
        if self._is_async:
            return self._async_dispatch(request, request_id)

        # sync 链：直接执行
        return self._sync_dispatch(request, request_id)

    async def _async_dispatch(self, request: HttpRequest, request_id: str) -> Any:
        try:
            response = await self.get_response(request)
            self._set_response_id(response, request_id)
            return response
        finally:
            self._cleanup()

    def _sync_dispatch(self, request: HttpRequest, request_id: str) -> Any:
        try:
            response = self.get_response(request)
            self._set_response_id(response, request_id)
            return response
        finally:
            self._cleanup()

    @staticmethod
    def _extract_request_id(request: HttpRequest) -> str:
        candidate = request.headers.get("X-Request-ID") or ""
        candidate = str(candidate).strip()
        if candidate and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate):
            return candidate
        return generate_request_id()

    @staticmethod
    def _set_response_id(response: HttpResponse, request_id: str) -> None:
        try:
            response.headers["X-Request-ID"] = request_id
        except Exception:
            with contextlib.suppress(Exception):
                response["X-Request-ID"] = request_id

    @staticmethod
    def _cleanup() -> None:
        clear_request_context()
        for attr in ("request_id", "trace_id"):
            if hasattr(threading.current_thread(), attr):
                with contextlib.suppress(Exception):
                    delattr(threading.current_thread(), attr)
