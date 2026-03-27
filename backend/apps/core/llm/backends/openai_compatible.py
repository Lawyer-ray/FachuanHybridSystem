"""OpenAI-compatible LLM backend."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import openai

from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError

from .siliconflow import SiliconFlowBackend

logger = logging.getLogger("apps.core.llm.backends.openai_compatible")


class OpenAICompatibleBackend(SiliconFlowBackend):
    """Generic backend for OpenAI-compatible providers (Moonshot/Kimi/DeepSeek etc.)."""

    BACKEND_NAME = "openai_compatible"

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

    def _resolve_embedding_model(self, model: str | None = None) -> str:
        if model and model.strip():
            return model.strip()
        if self._config and self._config.embedding_model and self._config.embedding_model.strip():
            return self._config.embedding_model.strip()
        configured = LLMConfig.get_openai_compatible_embedding_model().strip()
        if configured:
            return configured
        return self.default_model

    async def _build_async_client(self, timeout_seconds: float | None = None) -> openai.AsyncOpenAI:
        api_key = self._config.api_key if self._config and self._config.api_key else await LLMConfig.get_openai_compatible_api_key_async()
        base_url = self._config.base_url if self._config and self._config.base_url else await LLMConfig.get_openai_compatible_base_url_async()
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds or await LLMConfig.get_openai_compatible_timeout_async(),
        )

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


class MoonshotBackend(OpenAICompatibleBackend):
    """
    兼容历史后端名 moonshot。
    与 openai_compatible 共用实现，便于平滑迁移。
    """

    BACKEND_NAME = "moonshot"
