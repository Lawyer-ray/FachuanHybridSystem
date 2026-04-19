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


def _raise_all_unavailable(
    errors: list[Any],
    skipped: list[tuple[str, str]] | None = None,
) -> None:
    attempts_detail = [(n, str(e)) for n, e in errors]
    if skipped:
        attempts_detail.extend([(n, reason) for n, reason in skipped])
    raise LLMBackendUnavailableError(
        message="所有 LLM 后端均不可用",
        errors={"attempts": attempts_detail, "skipped": skipped or []},
    )


def _diagnose_unavailable(name: str, backend: ILLMBackend) -> str:
    """诊断后端不可用的原因,返回可读描述"""
    try:
        # SiliconFlow: 检查 API Key
        if name == "siliconflow":
            api_key = backend.api_key
            if not api_key:
                return "API Key 未配置"
            model = backend.default_model
            if not model:
                return "默认模型未配置"
            return f"is_available() 返回 False (api_key={'有' if api_key else '无'}, model={model!r})"
        # Ollama: 检查 base_url
        if name == "ollama":
            base_url = backend.base_url
            if not base_url:
                return "Base URL 未配置"
            return f"is_available() 返回 False (base_url={base_url!r})"
        # openai_compatible / moonshot
        api_key = getattr(backend, "api_key", None)
        if not api_key:
            return "API Key 未配置"
        return "is_available() 返回 False"
    except Exception as e:
        return f"诊断失败: {e}"


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
        skipped: list[tuple[str, str]] = []

        for name, backend_instance in backends_to_try:
            if not backend_instance.is_available():
                reason = _diagnose_unavailable(name, backend_instance)
                logger.warning("后端不可用,跳过", extra={"backend": name, "reason": reason})
                skipped.append((name, reason))
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

        _raise_all_unavailable(errors, skipped)
        raise AssertionError  # unreachable

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
        skipped: list[tuple[str, str]] = []

        for name, backend_instance in backends_to_try:
            if not backend_instance.is_available():
                reason = _diagnose_unavailable(name, backend_instance)
                logger.warning("后端不可用,跳过", extra={"backend": name, "reason": reason})
                skipped.append((name, reason))
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

        _raise_all_unavailable(errors, skipped)
        raise AssertionError  # unreachable
