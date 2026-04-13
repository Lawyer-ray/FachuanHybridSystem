"""Module for siliconflow."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

import httpx
import openai

from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError

from .base import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk, LLMUsage

logger = logging.getLogger("apps.core.llm.backends.siliconflow")


class SiliconFlowBackend:
    """
    SiliconFlow LLM 后端

    封装 OpenAI 兼容 API 调用逻辑,实现 ILLMBackend 接口.
    """

    BACKEND_NAME = "siliconflow"

    def __init__(self, config: BackendConfig | None = None) -> None:
        self._config = config
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._timeout: int | None = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            if self._config and self._config.api_key:
                self._api_key = self._config.api_key
            else:
                self._api_key = LLMConfig.get_api_key()
        return self._api_key

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            if self._config and self._config.base_url:
                self._base_url = self._config.base_url
            else:
                self._base_url = LLMConfig.get_base_url()
        return self._base_url

    @property
    def default_model(self) -> str:
        if self._default_model is None:
            if self._config and self._config.default_model:
                self._default_model = self._config.default_model
            else:
                self._default_model = LLMConfig.get_default_model()
        return self._default_model

    @property
    def timeout(self) -> int:
        if self._timeout is None:
            if self._config and self._config.timeout:
                self._timeout = self._config.timeout
            else:
                self._timeout = LLMConfig.get_timeout()
        return self._timeout

    def _normalize_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role not in {"system", "user", "assistant"}:
                role = "user"
            normalized.append({"role": role, "content": msg.get("content", "")})
        return normalized

    def _build_sync_client(self, timeout_seconds: float | None = None) -> openai.OpenAI:
        return openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout_seconds or self.timeout,
        )

    async def _build_async_client(self, timeout_seconds: float | None = None) -> openai.AsyncOpenAI:
        api_key = self._config.api_key if self._config and self._config.api_key else await LLMConfig.get_api_key_async()
        base_url = (
            self._config.base_url if self._config and self._config.base_url else await LLMConfig.get_base_url_async()
        )
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds or await LLMConfig.get_timeout_async(),
        )

    def _extract_usage(self, usage: Any) -> LLMUsage:
        if usage is None:
            return LLMUsage()
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _extract_content(self, response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        return str(content)

    def _resolve_embedding_model(self, model: str | None = None) -> str:
        if model and model.strip():
            return model.strip()
        if self._config and self._config.embedding_model and self._config.embedding_model.strip():
            return self._config.embedding_model.strip()
        if self._config and self._config.default_model and self._config.default_model.strip():
            return self._config.default_model.strip()
        return self.default_model

    def _raise_mapped_error(self, error: Exception, timeout_seconds: float, base_url: str) -> None:
        if isinstance(error, openai.AuthenticationError):
            logger.warning("SiliconFlow 认证失败", extra={"error": str(error)})
            raise LLMAuthenticationError(
                message="SiliconFlow API Key 无效或缺失", errors={"detail": str(error)}
            ) from error
        if isinstance(error, (openai.APITimeoutError, httpx.TimeoutException)):
            logger.warning("SiliconFlow 请求超时", extra={"timeout": timeout_seconds, "error": str(error)})
            raise LLMTimeoutError(
                message="LLM 请求超时",
                timeout_seconds=timeout_seconds,
                errors={"detail": str(error)},
            ) from error
        if isinstance(error, (openai.APIConnectionError, httpx.ConnectError)):
            logger.warning("SiliconFlow 网络连接失败", extra={"base_url": base_url, "error": str(error)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(error)}) from error
        if isinstance(error, (openai.APIError, openai.APIStatusError)):
            status_code = getattr(error, "status_code", None)
            logger.warning("SiliconFlow API 错误", extra={"status_code": status_code, "error": str(error)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {error!s}",
                status_code=status_code,
                errors={"detail": str(error)},
            ) from error
        logger.warning("SiliconFlow 调用异常", extra={"error": str(error), "error_type": type(error).__name__})
        raise LLMAPIError(message=f"LLM API 调用错误: {error!s}", errors={"detail": str(error)}) from error

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        used_model = model or self.default_model
        request_timeout = float(kwargs.pop("timeout_seconds", self.timeout))
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()
        try:
            client = self._build_sync_client(timeout_seconds=request_timeout)
            response = client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, request_timeout, self.base_url)

        duration_ms = (time.time() - start_time) * 1000
        usage = self._extract_usage(getattr(response, "usage", None))
        return LLMResponse(
            content=self._extract_content(response),
            model=used_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            duration_ms=duration_ms,
            backend=self.BACKEND_NAME,
        )

    async def achat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        used_model = model or (
            self._config.default_model if self._config else await LLMConfig.get_default_model_async()
        )
        request_timeout = float(
            kwargs.pop("timeout_seconds", self._config.timeout if self._config else await LLMConfig.get_timeout_async())
        )
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()
        try:
            async_client = await self._build_async_client(timeout_seconds=request_timeout)
            response = await async_client.chat.completions.create(**payload)
        except Exception as error:
            base_url = (
                self._config.base_url
                if self._config and self._config.base_url
                else await LLMConfig.get_base_url_async()
            )
            self._raise_mapped_error(error, request_timeout, base_url)

        duration_ms = (time.time() - start_time) * 1000
        usage = self._extract_usage(getattr(response, "usage", None))
        return LLMResponse(
            content=self._extract_content(response),
            model=used_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            duration_ms=duration_ms,
            backend=self.BACKEND_NAME,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[LLMStreamChunk]:
        used_model = model or self.default_model
        request_timeout = float(kwargs.pop("timeout_seconds", self.timeout))
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            client = self._build_sync_client(timeout_seconds=request_timeout)
            for chunk in client.chat.completions.create(**payload):
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", "") if delta is not None else ""
                    if content:
                        yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    final_usage = self._extract_usage(usage)
                    yield LLMStreamChunk(usage=final_usage, model=used_model, backend=self.BACKEND_NAME)
        except Exception as error:
            self._raise_mapped_error(error, request_timeout, self.base_url)

    async def astream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        used_model = model or (
            self._config.default_model if self._config else await LLMConfig.get_default_model_async()
        )
        request_timeout = float(
            kwargs.pop("timeout_seconds", self._config.timeout if self._config else await LLMConfig.get_timeout_async())
        )
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            async_client = await self._build_async_client(timeout_seconds=request_timeout)
            stream = await async_client.chat.completions.create(**payload)
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", "") if delta is not None else ""
                    if content:
                        yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    final_usage = self._extract_usage(usage)
                    yield LLMStreamChunk(usage=final_usage, model=used_model, backend=self.BACKEND_NAME)
        except Exception as error:
            base_url = (
                self._config.base_url
                if self._config and self._config.base_url
                else await LLMConfig.get_base_url_async()
            )
            self._raise_mapped_error(error, request_timeout, base_url)

    def get_default_embedding_model(self) -> str:
        return self._resolve_embedding_model()

    def embed_texts(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        if not texts:
            return []
        used_model = self._resolve_embedding_model(model)
        request_timeout = float(kwargs.pop("timeout_seconds", self.timeout))
        try:
            client = self._build_sync_client(timeout_seconds=request_timeout)
            response = client.embeddings.create(model=used_model, input=texts)
        except Exception as error:
            self._raise_mapped_error(error, request_timeout, self.base_url)

        vectors: list[list[float]] = []
        for item in getattr(response, "data", None) or []:
            vectors.append([float(v) for v in (getattr(item, "embedding", None) or [])])
        return vectors

    def get_default_model(self) -> str:
        return self.default_model

    def is_available(self) -> bool:
        api_key = self.api_key
        if not api_key:
            logger.debug("SiliconFlow 后端不可用:API Key 未配置")
            return False
        model = self.default_model
        if not model:
            logger.debug("SiliconFlow 后端不可用:默认模型未配置")
            return False
        return True


if TYPE_CHECKING:
    _backend: ILLMBackend = SiliconFlowBackend()  # type: ignore[assignment]
