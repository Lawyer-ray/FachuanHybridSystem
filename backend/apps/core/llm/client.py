"""Module for client."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from .backends import ILLMBackend, LLMResponse
from .tracking import record_llm_call

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, *, default_backend: str) -> None:
        self._default_backend = default_backend

    @staticmethod
    def _resolve_backend(backend: str | None, model: str | None, default_backend: str) -> str:
        """
        解析实际使用的后端.

        优先级: 显式指定 backend > 根据 model 推断 > 默认后端
        """
        if backend:
            return backend
        if model:
            from .config import LLMConfig

            resolved = LLMConfig.resolve_backend_for_model(model)
            logger.debug("根据模型自动路由后端", extra={"model": model, "backend": resolved})
            return resolved
        return default_backend

    @staticmethod
    def _record_success(response: LLMResponse, caller: str) -> None:
        """成功调用的审计记录（耗时直接采用后端返回的 duration_ms）。"""
        record_llm_call(
            backend=response.backend,
            model=response.model,
            duration_ms=response.duration_ms,
            success=True,
            caller=caller,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
        )

    @staticmethod
    def _record_failure(backend: str, model: str, started_at: float, caller: str, error: BaseException) -> None:
        record_llm_call(
            backend=backend,
            model=model or "-",
            duration_ms=(time.monotonic() - started_at) * 1000,
            success=False,
            caller=caller,
            error=error,
        )

    def complete(
        self,
        *,
        fallback_policy: Any,
        prompt: str,
        system_prompt: str | None = None,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(
            fallback_policy=fallback_policy,
            messages=messages,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
            caller=caller,
            **kwargs,
        )

    def chat(
        self,
        *,
        fallback_policy: Any,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        def operation(b: ILLMBackend) -> LLMResponse:
            return b.chat(messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)

        backend_name = self._resolve_backend(backend, model, self._default_backend)
        started_at = time.monotonic()
        try:
            response = cast(
                LLMResponse, fallback_policy.execute(operation=operation, backend=backend_name, fallback=fallback)
            )
        except Exception as error:
            self._record_failure(backend_name, model or "-", started_at, caller, error)
            raise
        self._record_success(response, caller)
        return response

    async def achat(
        self,
        *,
        fallback_policy: Any,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        async def operation(b: ILLMBackend) -> LLMResponse:
            return await b.achat(
                messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
            )

        backend_name = self._resolve_backend(backend, model, self._default_backend)
        started_at = time.monotonic()
        try:
            response = cast(
                LLMResponse,
                await fallback_policy.execute_async(operation=operation, backend=backend_name, fallback=fallback),
            )
        except Exception as error:
            self._record_failure(backend_name, model or "-", started_at, caller, error)
            raise
        self._record_success(response, caller)
        return response

    def embed_texts(
        self,
        *,
        fallback_policy: Any,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        caller: str = "",
        **kwargs: Any,
    ) -> list[list[float]]:
        def operation(b: ILLMBackend) -> list[list[float]]:
            return b.embed_texts(texts=texts, model=model, **kwargs)

        backend_name = backend or self._default_backend
        started_at = time.monotonic()
        try:
            result = cast(
                list[list[float]],
                fallback_policy.execute(operation=operation, backend=backend_name, fallback=fallback),
            )
        except Exception as error:
            self._record_failure(backend_name, model or "-", started_at, caller, error)
            raise
        record_llm_call(
            backend=backend_name,
            model=model or "-",
            duration_ms=(time.monotonic() - started_at) * 1000,
            success=True,
            caller=caller,
        )
        return result

    async def aembed_texts(
        self,
        *,
        fallback_policy: Any,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        caller: str = "",
        **kwargs: Any,
    ) -> list[list[float]]:
        async def operation(b: ILLMBackend) -> list[list[float]]:
            return await b.aembed_texts(texts=texts, model=model, **kwargs)

        backend_name = self._resolve_backend(backend, model, self._default_backend)
        started_at = time.monotonic()
        try:
            result = cast(
                list[list[float]],
                await fallback_policy.execute_async(operation=operation, backend=backend_name, fallback=fallback),
            )
        except Exception as error:
            self._record_failure(backend_name, model or "-", started_at, caller, error)
            raise
        record_llm_call(
            backend=backend_name,
            model=model or "-",
            duration_ms=(time.monotonic() - started_at) * 1000,
            success=True,
            caller=caller,
        )
        return result
