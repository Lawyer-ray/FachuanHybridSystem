"""Module for fallback policy."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .backends import ILLMBackend
from .circuit_breaker import CircuitBreaker
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
        # Ollama: 检查 base_url
        if name == "ollama":
            base_url = backend.base_url  # type: ignore[attr-defined]
            if not base_url:
                return "Base URL 未配置"
            return f"is_available() 返回 False (base_url={base_url!r})"
        # openai_compatible 及其他后端
        api_key = getattr(backend, "api_key", None)
        if not api_key:
            return "API Key 未配置"
        base_url = getattr(backend, "base_url", None)
        if not base_url:
            return "Base URL 未配置"
        model = getattr(backend, "default_model", None)
        if not model:
            return "默认模型未配置"
        return (
            f"is_available() 返回 False (api_key={'有' if api_key else '无'}, base_url={base_url!r}, model={model!r})"
        )
    except Exception as e:
        return f"诊断失败: {e}"


class LLMFallbackPolicy:
    """按优先级尝试后端,集成熔断与指数退避重试增强可靠性。

    - 熔断:超过连续失败阈值的后端进入短路冷却,冷却期内被跳过;
    - 退避:对可重试错误(超时/网络/API)在同一后端做有限次指数退避重试;
    - 默认 ``max_retries=0`` 不引入额外重试,保持既有“失败即切换”语义。
    """

    def __init__(
        self,
        *,
        router: LLMBackendRouter,
        breaker: CircuitBreaker | None = None,
        max_retries: int = 0,
        backoff_base: float = 1.0,
        backoff_factor: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries 必须 >= 0")
        if backoff_base < 0:
            raise ValueError("backoff_base 必须 >= 0")
        self.router = router
        self.breaker = breaker or CircuitBreaker()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.sleep = sleep

    def _run_with_retry(self, name: str, backend: ILLMBackend, operation: Callable[[ILLMBackend], TResult]) -> TResult:
        """在同一后端对可重试错误做指数退避重试,并同步熔断器状态。"""
        attempt = 0
        while True:
            try:
                result = operation(backend)
                self.breaker.record_success(name)
                return result
            except LLMAuthenticationError:
                # 认证错误为配置性问题,不可重试也不计入熔断
                raise
            except Exception as e:
                if not isinstance(e, _RETRIABLE_ERRORS):
                    self.breaker.record_failure(name)
                    raise
                self.breaker.record_failure(name)
                if attempt >= self.max_retries:
                    raise
                attempt += 1
                delay = self.backoff_base * (self.backoff_factor ** (attempt - 1))
                logger.warning(
                    "后端调用失败,退避后重试",
                    extra={"backend": name, "error": str(e), "attempt": attempt, "delay_sec": delay},
                )
                self.sleep(delay)

    def execute(
        self,
        *,
        operation: Callable[[ILLMBackend], TResult],
        backend: str | None = None,
        fallback: bool = True,
    ) -> TResult:
        if backend and not fallback:
            return self._run_with_retry(backend, self.router.get_backend(backend), operation)

        backends_to_try = _resolve_backends_from_router(self.router, backend, fallback)
        errors: list[tuple[str, Exception]] = []
        skipped: list[tuple[str, str]] = []

        for name, backend_instance in backends_to_try:
            if self.breaker.is_tripped(name):
                logger.info("后端短路冷却,跳过: backend=%s", name)
                skipped.append((name, "熔断冷却中"))
                continue
            if not backend_instance.is_available():
                reason = _diagnose_unavailable(name, backend_instance)
                logger.info("后端不可用,跳过: backend=%s, reason=%s", name, reason)
                skipped.append((name, reason))
                continue
            try:
                logger.info("尝试使用后端: %s", name)
                return self._run_with_retry(name, backend_instance, operation)
            except LLMAuthenticationError:
                raise
            except Exception as e:
                logger.exception("操作失败")
                _handle_call_error(name, e, fallback, errors)
                continue

        _raise_all_unavailable(errors, skipped)
        raise AssertionError  # unreachable

    async def _arun_with_retry(
        self,
        name: str,
        backend: ILLMBackend,
        operation: Callable[[ILLMBackend], Awaitable[TResult]],
    ) -> TResult:
        """异步版:`_run_with_retry``,重试间隙用 ``asyncio.sleep``。"""
        attempt = 0
        while True:
            try:
                result = await operation(backend)
                self.breaker.record_success(name)
                return result
            except LLMAuthenticationError:
                raise
            except Exception as e:
                if not isinstance(e, _RETRIABLE_ERRORS):
                    self.breaker.record_failure(name)
                    raise
                self.breaker.record_failure(name)
                if attempt >= self.max_retries:
                    raise
                attempt += 1
                delay = self.backoff_base * (self.backoff_factor ** (attempt - 1))
                logger.warning(
                    "后端调用失败,退避后重试",
                    extra={"backend": name, "error": str(e), "attempt": attempt, "delay_sec": delay},
                )
                await asyncio.sleep(delay)

    async def execute_async(
        self,
        *,
        operation: Callable[[ILLMBackend], Awaitable[TResult]],
        backend: str | None = None,
        fallback: bool = True,
    ) -> TResult:
        if backend and not fallback:
            return await self._arun_with_retry(backend, self.router.get_backend(backend), operation)

        backends_to_try = _resolve_backends_from_router(self.router, backend, fallback)
        errors: list[tuple[str, Exception]] = []
        skipped: list[tuple[str, str]] = []

        for name, backend_instance in backends_to_try:
            if self.breaker.is_tripped(name):
                logger.warning("后端短路冷却,跳过", extra={"backend": name})
                skipped.append((name, "熔断冷却中"))
                continue
            if not backend_instance.is_available():
                reason = _diagnose_unavailable(name, backend_instance)
                logger.warning("后端不可用,跳过", extra={"backend": name, "reason": reason})
                skipped.append((name, reason))
                continue
            try:
                logger.debug("异步尝试使用后端", extra={"backend": name})
                return await self._arun_with_retry(name, backend_instance, operation)
            except LLMAuthenticationError:
                raise
            except Exception as e:
                logger.exception("操作失败")
                _handle_call_error(name, e, fallback, errors)
                continue

        _raise_all_unavailable(errors, skipped)
        raise AssertionError  # unreachable
