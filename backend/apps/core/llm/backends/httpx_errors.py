"""Module for httpx errors."""

from __future__ import annotations

from typing import Any, NoReturn

import httpx

from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError


class HttpxErrorMixin:
    def raise_connect_error(
        self,
        *,
        backend_name: str,
        base_url: str,
        error: httpx.ConnectError,
        message: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> NoReturn:
        raise LLMNetworkError(
            message=message or f"无法连接到 {backend_name} 服务 ({base_url})",
            errors=errors or {"detail": str(error), "base_url": base_url},
        )

    def raise_timeout_error(
        self,
        *,
        backend_name: str,
        timeout: float,
        error: httpx.TimeoutException,
        message: str | None = None,
        errors: dict[str, Any] | None = None,
    ) -> NoReturn:
        raise LLMTimeoutError(
            message=message or f"{backend_name} 请求超时",
            timeout_seconds=timeout,
            errors=errors or {"detail": str(error)},
        )
