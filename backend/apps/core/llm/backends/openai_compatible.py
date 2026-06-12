"""OpenAI-compatible LLM backend."""

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

logger = logging.getLogger("apps.core.llm.backends.openai_compatible")


class OpenAICompatibleBackend:
    """Generic backend for OpenAI-compatible providers (Moonshot/Kimi/DeepSeek etc.)."""

    BACKEND_NAME = "openai_compatible"

    def __init__(self, config: BackendConfig | None = None) -> None:
        self._config = config
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._timeout: int | None = None

    # ── 配置属性 ─────────────────────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            if self._config and self._config.api_key:
                self._api_key = self._config.api_key
            else:
                self._api_key = LLMConfig.get_openai_compatible_api_key()
        return self._api_key

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            if self._config and self._config.base_url:
                self._base_url = self._config.base_url
            else:
                self._base_url = LLMConfig.get_openai_compatible_base_url()
        return self._base_url

    @property
    def default_model(self) -> str:
        if self._default_model is None:
            if self._config and self._config.default_model:
                self._default_model = self._config.default_model
            else:
                self._default_model = LLMConfig.get_openai_compatible_model()
        return self._default_model

    @property
    def timeout(self) -> int:
        if self._timeout is None:
            if self._config and self._config.timeout:
                self._timeout = self._config.timeout
            else:
                self._timeout = LLMConfig.get_openai_compatible_timeout()
        return self._timeout

    # ── 工具方法 ─────────────────────────────────────────────────────────────

    def _normalize_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role not in {"system", "user", "assistant"}:
                role = "user"
            normalized.append({"role": role, "content": msg.get("content", "")})
        return normalized

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
        content = getattr(message, "content", "") or ""
        # 部分推理模型（如 MiMo、DeepSeek R1）将输出放在 reasoning_content 字段
        if not content:
            reasoning = getattr(message, "reasoning_content", "") or ""
            if reasoning:
                return str(reasoning)
        if isinstance(content, str):
            return content
        return str(content)

    def _resolve_embedding_model(self, model: str | None = None) -> str:
        if model and model.strip():
            return model.strip()
        if self._config and self._config.embedding_model and self._config.embedding_model.strip():
            return self._config.embedding_model.strip()
        configured = LLMConfig.get_openai_compatible_embedding_model().strip()
        if configured:
            return configured
        return self.default_model

    # ── 客户端构建 ───────────────────────────────────────────────────────────

    def _build_sync_client(self, timeout_seconds: float | None = None) -> openai.OpenAI:
        # SSL 验证可通过环境变量 LLM_SSL_VERIFY=false 关闭（仅用于特殊 CDN/代理环境）
        import os

        ssl_verify = os.environ.get("LLM_SSL_VERIFY", "true").lower() not in ("false", "0", "no")
        transport = httpx.HTTPTransport(verify=ssl_verify)
        http_client = httpx.Client(transport=transport, timeout=timeout_seconds or self.timeout)
        return openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout_seconds or self.timeout,
            http_client=http_client,
        )

    async def _build_async_client(self, timeout_seconds: float | None = None) -> openai.AsyncOpenAI:
        api_key = (
            self._config.api_key
            if self._config and self._config.api_key
            else await LLMConfig.get_openai_compatible_api_key_async()
        )
        base_url = (
            self._config.base_url
            if self._config and self._config.base_url
            else await LLMConfig.get_openai_compatible_base_url_async()
        )
        timeout_val = timeout_seconds or await LLMConfig.get_openai_compatible_timeout_async()
        import os

        ssl_verify = os.environ.get("LLM_SSL_VERIFY", "true").lower() not in ("false", "0", "no")
        transport = httpx.AsyncHTTPTransport(verify=ssl_verify)
        http_async_client = httpx.AsyncClient(transport=transport, timeout=timeout_val)
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_val,
            http_client=http_async_client,
        )

    # ── 错误映射 ─────────────────────────────────────────────────────────────

    def _raise_mapped_error(self, error: Exception, timeout_seconds: float, base_url: str) -> None:
        provider_name = "OpenAI-compatible"
        if isinstance(error, openai.AuthenticationError):
            logger.warning("%s 认证失败", provider_name, extra={"error": str(error)})
            raise LLMAuthenticationError(
                message=f"{provider_name} API Key 无效或缺失",
                errors={"detail": str(error)},
            ) from error
        if isinstance(error, (openai.APITimeoutError, httpx.TimeoutException)):
            logger.warning("%s 请求超时", provider_name, extra={"timeout": timeout_seconds, "error": str(error)})
            raise LLMTimeoutError(
                message="LLM 请求超时",
                timeout_seconds=timeout_seconds,
                errors={"detail": str(error)},
            ) from error
        if isinstance(error, (openai.APIConnectionError, httpx.ConnectError)):
            logger.warning("%s 网络连接失败", provider_name, extra={"base_url": base_url, "error": str(error)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(error)}) from error
        if isinstance(error, (openai.APIError, openai.APIStatusError)):
            status_code = getattr(error, "status_code", None)
            logger.warning("%s API 错误", provider_name, extra={"status_code": status_code, "error": str(error)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {error!s}",
                status_code=status_code,
                errors={"detail": str(error)},
            ) from error
        logger.warning("%s 调用异常", provider_name, extra={"error": str(error), "error_type": type(error).__name__})
        raise LLMAPIError(message=f"LLM API 调用错误: {error!s}", errors={"detail": str(error)}) from error

    # ── thinking 模式控制 ────────────────────────────────────────────────────

    _DISABLE_THINKING_MODELS = {"kimi26", "mimo"}

    def _build_extra_body(self, model: str | None = None) -> dict[str, Any] | None:
        """vLLM/SGLang 部分模型（如 kimi26）需要 chat_template_kwargs 关闭思考模式"""
        used = (model or self.default_model).lower()
        if any(m in used for m in self._DISABLE_THINKING_MODELS):
            return {"chat_template_kwargs": {"thinking": False}}
        return None

    # ── API 方法 ─────────────────────────────────────────────────────────────

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
        extra = self._build_extra_body(used_model)
        if extra:
            payload["extra_body"] = extra

        start_time = time.time()
        try:
            client = self._build_sync_client(timeout_seconds=request_timeout)
            response = client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, request_timeout, self.base_url)

        duration_ms = (time.time() - start_time) * 1000
        usage = self._extract_usage(getattr(response, "usage", None))
        content = self._extract_content(response)
        logger.info(
            "OpenAICompatible.chat 响应: model=%s, content=%r, choices=%s, usage=%s",
            used_model,
            content,
            getattr(response, "choices", None),
            usage,
        )
        return LLMResponse(
            content=content,
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
            self._config.default_model if self._config else await LLMConfig.get_openai_compatible_model_async()
        )
        request_timeout = float(
            kwargs.pop(
                "timeout_seconds",
                self._config.timeout if self._config else await LLMConfig.get_openai_compatible_timeout_async(),
            )
        )
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        extra = self._build_extra_body(used_model)
        if extra:
            payload["extra_body"] = extra

        start_time = time.time()
        try:
            async_client = await self._build_async_client(timeout_seconds=request_timeout)
            response = await async_client.chat.completions.create(**payload)
        except Exception as error:
            base_url = (
                self._config.base_url
                if self._config and self._config.base_url
                else await LLMConfig.get_openai_compatible_base_url_async()
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
        extra = self._build_extra_body(used_model)
        if extra:
            payload["extra_body"] = extra

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
            self._config.default_model if self._config else await LLMConfig.get_openai_compatible_model_async()
        )
        request_timeout = float(
            kwargs.pop(
                "timeout_seconds",
                self._config.timeout if self._config else await LLMConfig.get_openai_compatible_timeout_async(),
            )
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
        extra = self._build_extra_body(used_model)
        if extra:
            payload["extra_body"] = extra

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
                else await LLMConfig.get_openai_compatible_base_url_async()
            )
            self._raise_mapped_error(error, request_timeout, base_url)

    # ── 接口方法 ─────────────────────────────────────────────────────────────

    def get_default_model(self) -> str:
        return self.default_model

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

    def is_available(self) -> bool:
        if self._config and not self._config.enabled:
            logger.debug("OpenAI-compatible 后端不可用:已在配置中禁用")
            return False
        api_key = self.api_key
        if not api_key:
            logger.debug("OpenAI-compatible 后端不可用:API Key 未配置")
            return False
        model = self.default_model
        if not model:
            logger.debug("OpenAI-compatible 后端不可用:默认模型未配置")
            return False
        return True


if TYPE_CHECKING:
    _backend: ILLMBackend = OpenAICompatibleBackend()  # type: ignore[assignment]
