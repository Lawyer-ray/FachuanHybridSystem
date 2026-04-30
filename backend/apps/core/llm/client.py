"""Module for client."""

from __future__ import annotations

import logging
from typing import Any, cast

from .backends import ILLMBackend, LLMResponse

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
        **kwargs: Any,
    ) -> LLMResponse:
        def operation(b: ILLMBackend) -> LLMResponse:
            return b.chat(messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)

        backend_name = self._resolve_backend(backend, model, self._default_backend)
        return cast(LLMResponse, fallback_policy.execute(operation=operation, backend=backend_name, fallback=fallback))

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
        **kwargs: Any,
    ) -> LLMResponse:
        async def operation(b: ILLMBackend) -> LLMResponse:
            return await b.achat(
                messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
            )

        backend_name = self._resolve_backend(backend, model, self._default_backend)
        return cast(
            LLMResponse,
            await fallback_policy.execute_async(operation=operation, backend=backend_name, fallback=fallback),
        )

    def embed_texts(
        self,
        *,
        fallback_policy: Any,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> list[list[float]]:
        def operation(b: ILLMBackend) -> list[list[float]]:
            return b.embed_texts(texts=texts, model=model, **kwargs)

        backend_name = backend or self._default_backend
        return cast(
            list[list[float]],
            fallback_policy.execute(operation=operation, backend=backend_name, fallback=fallback),
        )
