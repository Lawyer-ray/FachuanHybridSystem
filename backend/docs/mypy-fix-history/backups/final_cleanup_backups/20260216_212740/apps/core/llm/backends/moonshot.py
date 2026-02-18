"""Module for moonshot."""

from __future__ import annotations

"""
Moonshot LLM 后端实现

封装 Moonshot API 调用逻辑,实现 ILLMBackend 接口.
支持文件上传、检索、提取操作,保留异步方法.

Requirements: 3.1, 3.2, 3.3
"""

import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import httpx

from apps.core.httpx_clients import get_async_http_client, get_sync_http_client
from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError

from .base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from .http_error_summary import summarize_http_error_response
from .httpx_errors import HttpxErrorMixin
from .moonshot_files import MoonshotFilesClient

logger = logging.getLogger("apps.core.llm.backends.moonshot")


class MoonshotBackend(HttpxErrorMixin):
    """
    Moonshot LLM 后端

    封装 Moonshot API 调用,实现 ILLMBackend 接口.
    支持文件上传、检索、提取操作.

    Example:
        backend = MoonshotBackend()

        # 聊天
        response = backend.chat([{"role": "user", "content": "你好"}])
        print(response.content)

        # 文件上传
        file_info = backend.upload_file("/path/to/file.pdf")
        print(file_info["id"])

        # 文件提取
        extraction = backend.extract_result(file_info["id"])
        print(extraction["content"])

    Requirements: 3.1, 3.2, 3.3
    """

    BACKEND_NAME = "moonshot"
    DEFAULT_MODEL = "moonshot-v1-auto"
    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_TIMEOUT = 120.0

    def __init__(self, config: BackendConfig | None = None) -> None:
        """
        初始化 Moonshot 后端

        Args:
            config: 后端配置,None 时从环境变量读取
        """
        self._config = config
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._timeout: float | None = None
        self._moonshot_files_client: MoonshotFilesClient | None = None

    @property
    def api_key(self) -> str:
        """获取 API Key(延迟加载)"""
        if self._api_key is None:
            if self._config and self._config.api_key:
                self._api_key = self._config.api_key
            else:
                self._api_key = LLMConfig.get_moonshot_api_key()
        return self._api_key

    @property
    def base_url(self) -> str:
        """获取 Base URL(延迟加载)"""
        if self._base_url is None:
            if self._config and self._config.base_url:
                self._base_url = self._config.base_url
            else:
                self._base_url = LLMConfig.get_moonshot_base_url()
        return self._base_url

    @property
    def default_model(self) -> str:
        """获取默认模型(延迟加载)"""
        if self._default_model is None:
            if self._config and self._config.default_model:
                self._default_model = self._config.default_model
            else:
                self._default_model = LLMConfig.get_moonshot_default_model()
        return self._default_model

    @property
    def timeout(self) -> float:
        """获取超时时间(延迟加载)"""
        if self._timeout is None:
            if self._config and self._config.timeout:
                self._timeout = float(self._config.timeout)
            else:
                self._timeout = float(LLMConfig.get_moonshot_timeout() or self.DEFAULT_TIMEOUT)
        return self._timeout

    def _get_headers(self) -> dict[str, str]:
        """获取请求头"""
        return {"Authorization": f"Bearer {self.api_key}"}

    def _handle_http_error(
        self,
        error: httpx.HTTPStatusError,
        operation: str,
    ) -> None:
        """
        处理 HTTP 错误

        Args:
            error: HTTP 状态错误
            operation: 操作名称(用于日志)

        Raises:
            LLMAuthenticationError: 认证失败
            LLMAPIError: API 错误
        """
        status_code = error.response.status_code
        summary = summarize_http_error_response(error.response)

        if status_code == 401:
            logger.warning("Moonshot 认证失败", extra={"operation": operation, **summary})
            raise LLMAuthenticationError(
                message="Moonshot API Key 无效或缺失",
                errors=summary,
            )

        logger.warning(
            "Moonshot API 错误",
            extra={
                "operation": operation,
                **summary,
            },
        )
        raise LLMAPIError(
            message=f"Moonshot API 错误 ({status_code})",
            status_code=status_code,
            errors=summary,
        )

    def _handle_connect_error(self, error: httpx.ConnectError) -> None:
        """
        处理连接错误

        Args:
            error: 连接错误

        Raises:
            LLMNetworkError: 网络错误
        """
        logger.warning("Moonshot 网络连接失败", extra={"base_url": self.base_url, "error": str(error)})
        self.raise_connect_error(
            backend_name="Moonshot",
            base_url=self.base_url,
            error=error,
            message=f"无法连接到 Moonshot 服务 ({self.base_url})",
        )

    def _handle_timeout_error(
        self,
        error: httpx.TimeoutException,
        timeout: float,
    ) -> None:
        """
        处理超时错误

        Args:
            error: 超时错误
            timeout: 超时时间

        Raises:
            LLMTimeoutError: 超时错误
        """
        logger.warning("Moonshot 请求超时", extra={"timeout": timeout, "error": str(error)})
        self.raise_timeout_error(
            backend_name="Moonshot",
            timeout=timeout,
            error=error,
            message="Moonshot 请求超时",
        )

    def _build_llm_response(
        self,
        data: dict[str, Any],
        model: str,
        duration_ms: float,
    ) -> LLMResponse:
        """
        构建 LLMResponse 对象

        Args:
            data: Moonshot API 响应数据
            model: 使用的模型名称
            duration_ms: 调用耗时(毫秒)

        Returns:
            LLMResponse 对象
        """
        # 提取内容
        choices = data.get("choices", [])
        content = ""
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")

        # 提取 token 使用信息
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            backend=self.BACKEND_NAME,
        )

    # ==================== ILLMBackend 接口实现 ====================

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
            **kwargs: 额外参数

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        used_model = model or self.default_model
        request_timeout = kwargs.pop("timeout", None) or self.timeout

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": messages,
        }

        if temperature != 0.7:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()

        try:
            client = get_sync_http_client()
            resp = client.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=request_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, "chat")
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except Exception as e:
            logger.warning("Moonshot 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Moonshot API 时发生错误: {e!s}", errors={"detail": str(e)}) from e

        duration_ms = (time.time() - start_time) * 1000

        return self._build_llm_response(data, used_model, duration_ms)

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
            **kwargs: 额外参数

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        used_model = model or self.default_model
        request_timeout = kwargs.pop("timeout", None) or self.timeout

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": used_model,
            "messages": messages,
        }

        if temperature != 0.7:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()

        try:
            client = get_async_http_client()
            resp = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=request_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, "achat")
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except Exception as e:
            logger.warning("Moonshot 异步调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Moonshot API 时发生错误: {e!s}", errors={"detail": str(e)}) from e

        duration_ms = (time.time() - start_time) * 1000

        return self._build_llm_response(data, used_model, duration_ms)

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[LLMStreamChunk]:
        resp = self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        yield LLMStreamChunk(content=resp.content, model=resp.model, backend=self.BACKEND_NAME)
        yield LLMStreamChunk(
            usage=LLMUsage(
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                total_tokens=resp.total_tokens,
            ),
            model=resp.model,
            backend=self.BACKEND_NAME,
        )

    async def astream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        resp = await self.achat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        yield LLMStreamChunk(content=resp.content, model=resp.model, backend=self.BACKEND_NAME)
        yield LLMStreamChunk(
            usage=LLMUsage(
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                total_tokens=resp.total_tokens,
            ),
            model=resp.model,
            backend=self.BACKEND_NAME,
        )

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
            logger.debug("Moonshot 后端不可用:API Key 未配置")
            return False
        return True

    # ==================== 文件操作接口 ====================

    @property
    def _files_client(self) -> MoonshotFilesClient:
        if self._moonshot_files_client is None:
            self._moonshot_files_client = MoonshotFilesClient(self)  # type: ignore[arg-type]
        return self._moonshot_files_client

    def upload_file(self, file_path: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._files_client.upload_file(file_path))

    async def aupload_file(self, file_path: str) -> dict[str, Any]:
        return cast(dict[str, Any], await self._files_client.aupload_file(file_path))

    def list_files(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._files_client.list_files())

    async def alist_files(self) -> dict[str, Any]:
        return cast(dict[str, Any], await self._files_client.alist_files())

    def retrieve_file(self, file_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._files_client.retrieve_file(file_id))

    async def aretrieve_file(self, file_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], await self._files_client.aretrieve_file(file_id))

    def extract_result(self, file_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._files_client.extract_result(file_id))

    async def aextract_result(self, file_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], await self._files_client.aextract_result(file_id))
