"""Module for fallback policy."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .backends import ILLMBackend
from .exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)
from .router import LLMBackendRouter

logger = logging.getLogger("apps.core.llm.service")

_RETRIABLE_ERRORS = (LLMTimeoutError, LLMNetworkError, LLMAPIError)
TResult = TypeVar("TResult")


def _resolve_backends_from_router(
    router: LLMBackendRouter, backend: str | None, fallback: bool
) -> list[tuple[str, ILLMBackend]]:
    """解析要尝试的后端列表"""
    if backend:
        result = [(backend, router.get_backend(backend))]
        if fallback:
            for name, b in router.get_backends_by_priority():
                if name != backend:
                    result.append((name, b))
        return result
    return router.get_backends_by_priority()


def _handle_call_error(name: str, e: Exception, fallback: bool, errors: list[Any]) -> None:
    """处理后端调用错误,决定是否继续尝试"""
    errors.append((name, e))
    if isinstance(e, _RETRIABLE_ERRORS):
        logger.warning(
            "后端调用失败,尝试下一个",
            extra={"backend": name, "error": str(e), "error_type": type(e).__name__},
        )
        if not fallback:
            raise
    else:
        logger.warning(
            "后端调用发生未知错误",
            extra={"backend": name, "error": str(e), "error_type": type(e).__name__},
        )
        if not fallback:
            raise LLMAPIError(message=f"调用后端 {name} 时发生错误: {e!s}", errors={"detail": str(e)}) from e


def _raise_all_unavailable(errors: list[Any]) -> None:
    raise LLMBackendUnavailableError(
        message="所有 LLM 后端均不可用", errors={"attempts": [(n, str(e)) for n, e in errors]}
    )


class LLMFallbackPolicy:
    def __init__(self, *, router: LLMBackendRouter) -> None:
        self.router = router

    def execute(
        self,
        *,
        operation: Callable[[ILLMBackend], TResult],
        backend: str | None = None,
        fallback: bool = True,
    ) -> TResult:
        if backend and not fallback:
            return operation(self.router.get_backend(backend))

        backends_to_try = _resolve_backends_from_router(self.router, backend, fallback)
        errors: list[tuple[str, Exception]] = []

        for name, backend_instance in backends_to_try:
            if not backend_instance.is_available():
                logger.debug("后端不可用,跳过", extra={"backend": name})
                continue
            try:
                logger.debug("尝试使用后端", extra={"backend": name})
                return operation(backend_instance)
            except LLMAuthenticationError:
                raise
            except Exception as e:
                logger.exception("操作失败")
                _handle_call_error(name, e, fallback, errors)
                continue

        _raise_all_unavailable(errors)

    async def execute_async(
        self,
        *,
        operation: Callable[[ILLMBackend], Awaitable[TResult]],
        backend: str | None = None,
        fallback: bool = True,
    ) -> TResult:
        if backend and not fallback:
            return await operation(self.router.get_backend(backend))

        backends_to_try = _resolve_backends_from_router(self.router, backend, fallback)
        errors: list[tuple[str, Exception]] = []

        for name, backend_instance in backends_to_try:
            if not backend_instance.is_available():
                logger.debug("后端不可用,跳过", extra={"backend": name})
                continue
            try:
                logger.debug("异步尝试使用后端", extra={"backend": name})
                return await operation(backend_instance)
            except LLMAuthenticationError:
                raise
            except Exception as e:
                logger.exception("操作失败")
                _handle_call_error(name, e, fallback, errors)
                continue

        _raise_all_unavailable(errors)
