"""Module for siliconflow."""

from __future__ import annotations

"\nSiliconFlow LLM 后端实现\n\n封装 SiliconFlow API 调用逻辑,实现 ILLMBackend 接口.\n\nRequirements: 1.2, 1.5\n"
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, Literal

import httpx
import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError

from .base import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk, LLMUsage

logger = logging.getLogger("apps.core.llm.backends.siliconflow")


class SiliconFlowBackend:
    """
    SiliconFlow LLM 后端

    封装 LangChain + SiliconFlow API,实现 ILLMBackend 接口.

    Example:
        backend = SiliconFlowBackend()
        response = backend.chat([{"role": "user", "content": "你好"}])
        logger.info(response.content)

    Requirements: 1.2, 1.5
    """

    BACKEND_NAME = "siliconflow"

    def __init__(self, config: BackendConfig | None = None) -> None:
        """
        初始化 SiliconFlow 后端

        Args:
            config: 后端配置,None 时从 LLMConfig 读取
        """
        self._config = config
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._timeout: int | None = None

    @property
    def api_key(self) -> str:
        """获取 API Key(延迟加载)"""
        if self._api_key is None:
            if self._config and self._config.api_key:
                self._api_key = self._config.api_key
            else:
                self._api_key = LLMConfig.get_api_key()
        return self._api_key

    @property
    def base_url(self) -> str:
        """获取 Base URL(延迟加载)"""
        if self._base_url is None:
            if self._config and self._config.base_url:
                self._base_url = self._config.base_url
            else:
                self._base_url = LLMConfig.get_base_url()
        return self._base_url

    @property
    def default_model(self) -> str:
        """获取默认模型(延迟加载)"""
        if self._default_model is None:
            if self._config and self._config.default_model:
                self._default_model = self._config.default_model
            else:
                self._default_model = LLMConfig.get_default_model()
        return self._default_model

    @property
    def timeout(self) -> int:
        """获取超时时间(延迟加载)"""
        if self._timeout is None:
            if self._config and self._config.timeout:
                self._timeout = self._config.timeout
            else:
                self._timeout = LLMConfig.get_timeout()
        return self._timeout

    def _convert_messages(self, messages: list[dict[str, str]]) -> list[Any]:
        """
        将消息字典列表转换为 LangChain 消息对象列表

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]

        Returns:
            LangChain 消息对象列表
        """
        langchain_messages: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))
        return langchain_messages

    def _extract_token_usage(self, response_metadata: dict[str, Any]) -> tuple[Any, ...]:
        """
        从响应元数据中提取 token 使用信息

        Args:
            response_metadata: 响应元数据

        Returns:
            (prompt_tokens, completion_tokens, total_tokens) 元组
        """
        token_usage = response_metadata.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        total_tokens = token_usage.get("total_tokens", prompt_tokens + completion_tokens)
        return (prompt_tokens, completion_tokens, total_tokens)

    def _extract_usage_from_chunk(self, chunk: Any) -> LLMUsage | None:
        usage_metadata = getattr(chunk, "usage_metadata", None)
        if not usage_metadata or not isinstance(usage_metadata, dict):
            return None
        prompt_tokens = usage_metadata.get("input_tokens") or usage_metadata.get("prompt_tokens") or 0
        completion_tokens = usage_metadata.get("output_tokens") or usage_metadata.get("completion_tokens") or 0
        total_tokens = usage_metadata.get("total_tokens")
        if total_tokens is None:
            total_tokens = int(prompt_tokens) + int(completion_tokens)
        return LLMUsage(
            prompt_tokens=int(prompt_tokens), completion_tokens=int(completion_tokens), total_tokens=int(total_tokens)
        )

    def _create_llm(
        self, model: str | None = None, temperature: float = 0.7, max_tokens: int | None = None
    ) -> ChatOpenAI:
        """
        创建 ChatOpenAI 实例

        Args:
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 token 数

        Returns:
            ChatOpenAI 实例
        """
        return ChatOpenAI(  # type: ignore[call-arg]
            api_key=SecretStr(self.api_key),
            base_url=self.base_url,
            model=model or self.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        同步聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称,None 时使用默认模型
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            **kwargs: 额外参数(忽略)

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        used_model = model or self.default_model
        llm = self._create_llm(model=used_model, temperature=temperature, max_tokens=max_tokens)
        langchain_messages = self._convert_messages(messages)
        start_time = time.time()
        try:
            response = llm.invoke(langchain_messages)
        except openai.AuthenticationError as e:
            logger.warning("SiliconFlow 认证失败", extra={"error": str(e)})
            raise LLMAuthenticationError(message="SiliconFlow API Key 无效或缺失", errors={"detail": str(e)}) from e
        except (openai.APITimeoutError, httpx.TimeoutException) as e:
            logger.warning("SiliconFlow 请求超时", extra={"timeout": self.timeout, "error": str(e)})
            raise LLMTimeoutError(
                message="LLM 请求超时", timeout_seconds=self.timeout, errors={"detail": str(e)}
            ) from e
        except httpx.ConnectError as e:
            logger.warning("SiliconFlow 网络连接失败", extra={"base_url": self.base_url, "error": str(e)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(e)}) from e
        except (openai.APIError, openai.APIStatusError) as e:
            status_code = getattr(e, "status_code", None)
            logger.warning("SiliconFlow API 错误", extra={"status_code": status_code, "error": str(e)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {e!s}", status_code=status_code, errors={"detail": str(e)}
            ) from e
        duration_ms = (time.time() - start_time) * 1000
        prompt_tokens, completion_tokens, total_tokens = self._extract_token_usage(response.response_metadata)
        content_str = response.content if isinstance(response.content, str) else str(response.content)
        return LLMResponse(
            content=content_str,
            model=used_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
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
        """
        异步聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称,None 时使用默认模型
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            **kwargs: 额外参数(忽略)

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        api_key = self._config.api_key if self._config and self._config.api_key else await LLMConfig.get_api_key_async()
        base_url = (
            self._config.base_url if self._config and self._config.base_url else await LLMConfig.get_base_url_async()
        )
        default_model = (
            self._config.default_model
            if self._config and self._config.default_model
            else await LLMConfig.get_default_model_async()
        )
        timeout = self._config.timeout if self._config and self._config.timeout else await LLMConfig.get_timeout_async()
        used_model = model or default_model
        llm = ChatOpenAI(  # type: ignore[call-arg]
            api_key=SecretStr(api_key),
            base_url=base_url,
            model=used_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        langchain_messages = self._convert_messages(messages)
        start_time = time.time()
        try:
            response = await llm.ainvoke(langchain_messages)
        except openai.AuthenticationError as e:
            logger.warning("SiliconFlow 认证失败", extra={"error": str(e)})
            raise LLMAuthenticationError(message="SiliconFlow API Key 无效或缺失", errors={"detail": str(e)}) from e
        except httpx.TimeoutException as e:
            logger.warning("SiliconFlow 请求超时", extra={"timeout": timeout, "error": str(e)})
            raise LLMTimeoutError(message="LLM 请求超时", timeout_seconds=timeout, errors={"detail": str(e)}) from e
        except httpx.ConnectError as e:
            logger.warning("SiliconFlow 网络连接失败", extra={"base_url": base_url, "error": str(e)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(e)}) from e
        except (openai.APIError, openai.APIStatusError) as e:
            status_code = getattr(e, "status_code", None)
            logger.warning("SiliconFlow API 错误", extra={"status_code": status_code, "error": str(e)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {e!s}", status_code=status_code, errors={"detail": str(e)}
            ) from e
        duration_ms = (time.time() - start_time) * 1000
        prompt_tokens, completion_tokens, total_tokens = self._extract_token_usage(response.response_metadata)
        content_str = response.content if isinstance(response.content, str) else str(response.content)
        return LLMResponse(
            content=content_str,
            model=used_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
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
        llm = self._create_llm(model=used_model, temperature=temperature, max_tokens=max_tokens)
        langchain_messages = self._convert_messages(messages)
        try:
            for chunk in llm.stream(langchain_messages):
                content = getattr(chunk, "content", "") or ""
                usage = self._extract_usage_from_chunk(chunk)
                yield LLMStreamChunk(content=content, usage=usage, model=used_model, backend=self.BACKEND_NAME)
        except openai.AuthenticationError as e:
            logger.warning("SiliconFlow 认证失败", extra={"error": str(e)})
            raise LLMAuthenticationError(message="SiliconFlow API Key 无效或缺失", errors={"detail": str(e)}) from e
        except httpx.TimeoutException as e:
            logger.warning("SiliconFlow 请求超时", extra={"timeout": self.timeout, "error": str(e)})
            raise LLMTimeoutError(
                message="LLM 请求超时", timeout_seconds=self.timeout, errors={"detail": str(e)}
            ) from e
        except httpx.ConnectError as e:
            logger.warning("SiliconFlow 网络连接失败", extra={"base_url": self.base_url, "error": str(e)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(e)}) from e
        except (openai.APIError, openai.APIStatusError) as e:
            status_code = getattr(e, "status_code", None)
            logger.warning("SiliconFlow API 错误", extra={"status_code": status_code, "error": str(e)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {e!s}", status_code=status_code, errors={"detail": str(e)}
            ) from e

    async def astream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        api_key = self._config.api_key if self._config and self._config.api_key else await LLMConfig.get_api_key_async()
        base_url = (
            self._config.base_url if self._config and self._config.base_url else await LLMConfig.get_base_url_async()
        )
        default_model = (
            self._config.default_model
            if self._config and self._config.default_model
            else await LLMConfig.get_default_model_async()
        )
        timeout = self._config.timeout if self._config and self._config.timeout else await LLMConfig.get_timeout_async()
        used_model = model or default_model
        llm = ChatOpenAI(  # type: ignore[call-arg]
            api_key=SecretStr(api_key),
            base_url=base_url,
            model=used_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        langchain_messages = self._convert_messages(messages)
        try:
            async for chunk in llm.astream(langchain_messages):
                content = getattr(chunk, "content", "") or ""
                usage = self._extract_usage_from_chunk(chunk)
                yield LLMStreamChunk(content=content, usage=usage, model=used_model, backend=self.BACKEND_NAME)
        except openai.AuthenticationError as e:
            logger.warning("SiliconFlow 认证失败", extra={"error": str(e)})
            raise LLMAuthenticationError(message="SiliconFlow API Key 无效或缺失", errors={"detail": str(e)}) from e
        except httpx.TimeoutException as e:
            logger.warning("SiliconFlow 请求超时", extra={"timeout": timeout, "error": str(e)})
            raise LLMTimeoutError(message="LLM 请求超时", timeout_seconds=timeout, errors={"detail": str(e)}) from e
        except httpx.ConnectError as e:
            logger.warning("SiliconFlow 网络连接失败", extra={"base_url": base_url, "error": str(e)})
            raise LLMNetworkError(message="LLM 网络连接失败", errors={"detail": str(e)}) from e
        except (openai.APIError, openai.APIStatusError) as e:
            status_code = getattr(e, "status_code", None)
            logger.warning("SiliconFlow API 错误", extra={"status_code": status_code, "error": str(e)})
            raise LLMAPIError(
                message=f"LLM API 调用错误: {e!s}", status_code=status_code, errors={"detail": str(e)}
            ) from e

    def get_default_model(self) -> str:
        """
        获取默认模型名称

        Returns:
            str: 后端的默认模型名称
        """
        return self.default_model

    def is_available(self) -> bool:
        """
        检查后端是否可用

        检查 API Key 是否已配置.

        Returns:
            bool: True 表示后端可用,False 表示不可用
        """
        api_key = self.api_key
        if not api_key:
            logger.debug("SiliconFlow 后端不可用:API Key 未配置")
            return False
        return True

    def get_langchain_llm(
        self, model: str | None = None, temperature: float | None = None, max_tokens: int | None = None
    ) -> ChatOpenAI:
        """
        获取原生 LangChain LLM 实例

        用于构建复杂的 LCEL 链.

        Args:
            model: 模型名称,None 时使用默认模型
            temperature: 温度参数,None 时使用配置默认值
            max_tokens: 最大输出 token 数,None 时使用配置默认值

        Returns:
            ChatOpenAI 实例
        """
        return ChatOpenAI(  # type: ignore[call-arg]
            api_key=SecretStr(self.api_key),
            base_url=self.base_url,
            model=model or self.default_model,
            temperature=temperature if temperature is not None else LLMConfig.get_temperature(),
            max_tokens=max_tokens if max_tokens is not None else LLMConfig.get_max_tokens(),
            timeout=self.timeout,
        )

    def get_structured_llm(
        self,
        schema: type,
        model: str | None = None,
        method: Literal["function_calling", "json_mode", "json_schema"] = "json_mode",
    ) -> Any:
        """
        获取支持结构化输出的 LLM 实例

        Args:
            schema: Pydantic 模型类,定义输出结构
            model: 模型名称,None 时使用默认模型
            method: 结构化输出方法 (json_mode/function_calling/json_schema)

        Returns:
            绑定了结构化输出的 Runnable 实例
        """
        llm = self.get_langchain_llm(model=model)
        return llm.with_structured_output(schema, method=method)


if TYPE_CHECKING:
    _backend: ILLMBackend = SiliconFlowBackend()  # type: ignore[assignment]
