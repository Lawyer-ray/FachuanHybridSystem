"""Module for ollama."""

from __future__ import annotations

"""
Ollama LLM 后端实现

封装 Ollama API 调用逻辑,实现 ILLMBackend 接口.
支持 chat_with_options 的 num_predict, timeout 参数.

Requirements: 2.1, 2.2, 2.3, 1.6
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

import httpx

from apps.core.httpx_clients import get_async_http_client, get_sync_http_client
from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError

from .base import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk, LLMUsage
from .http_error_summary import summarize_http_error_response
from .httpx_errors import HttpxErrorMixin
from .ollama_protocol import build_ollama_chat_payload, parse_ollama_chat_response

logger = logging.getLogger("apps.core.llm.backends.ollama")


class OllamaBackend(HttpxErrorMixin):
    """
    Ollama LLM 后端

    封装 Ollama API 调用,实现 ILLMBackend 接口.
    支持 chat_with_options 的 num_predict, timeout 参数.

    Example:
        backend = OllamaBackend()
        response = backend.chat([{"role": "user", "content": "你好"}])
        logger.info(response.content)

        # 使用 options 参数
        response = backend.chat(
            [{"role": "user", "content": "你好"}],
            num_predict=100,
            timeout=60.0
        )

    Requirements: 2.1, 2.2, 2.3, 1.6
    """

    BACKEND_NAME = "ollama"
    DEFAULT_MODEL = "qwen3:0.6b"
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_TIMEOUT = 120.0

    def __init__(self, config: BackendConfig | None = None) -> None:
        """
        初始化 Ollama 后端

        Args:
            config: 后端配置,None 时从 Django settings 读取
        """
        self._config = config
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._default_embedding_model: str | None = None
        self._timeout: float | None = None

    @property
    def base_url(self) -> str:
        """获取 Base URL(延迟加载)"""
        if self._base_url is None:
            if self._config and self._config.base_url:
                self._base_url = self._config.base_url
            else:
                self._base_url = LLMConfig.get_ollama_base_url()
        return self._base_url

    @property
    def default_model(self) -> str:
        """获取默认模型(延迟加载)"""
        if self._default_model is None:
            if self._config and self._config.default_model:
                self._default_model = self._config.default_model
            else:
                self._default_model = LLMConfig.get_ollama_model()
        return self._default_model

    @property
    def timeout(self) -> float:
        """获取超时时间(延迟加载)"""
        if self._timeout is None:
            if self._config and self._config.timeout:
                self._timeout = float(self._config.timeout)
            else:
                self._timeout = float(LLMConfig.get_ollama_timeout())
        return self._timeout

    @property
    def default_embedding_model(self) -> str:
        if self._default_embedding_model is None:
            if self._config and self._config.embedding_model:
                self._default_embedding_model = self._config.embedding_model
            else:
                self._default_embedding_model = self.default_model
        return self._default_embedding_model

    def _build_api_url(self) -> str:
        """构建 API URL"""
        return self.base_url.rstrip("/") + "/api/chat"

    def _build_embed_url(self) -> str:
        return self.base_url.rstrip("/") + "/api/embed"

    def _build_legacy_embed_url(self) -> str:
        return self.base_url.rstrip("/") + "/api/embeddings"

    def _handle_http_error(
        self,
        error: httpx.HTTPStatusError,
        model: str,
    ) -> None:
        """
        处理 HTTP 错误

        Args:
            error: HTTP 状态错误
            model: 使用的模型名称

        Raises:
            LLMAPIError: API 错误
        """
        status_code = error.response.status_code

        if status_code == 404:
            logger.warning(
                "Ollama API 未找到",
                extra={
                    "base_url": self.base_url,
                    "model": model,
                    "status_code": status_code,
                },
            )
            raise LLMAPIError(
                message=(
                    f"Ollama API 未找到 (404).请检查:\n"
                    f"1. Ollama 服务是否运行在 {self.base_url}\n"
                    f"2. 模型 '{model}' 是否已安装 (运行: ollama pull {model})\n"
                    f"3. API 路径是否正确"
                ),
                status_code=status_code,
                errors={"model": model, "base_url": self.base_url},
            )

        summary = summarize_http_error_response(error.response)
        logger.warning(
            "Ollama API 错误",
            extra={
                "model": model,
                **summary,
            },
        )
        raise LLMAPIError(
            message=f"Ollama API 错误 ({status_code})",
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
        logger.warning("Ollama 网络连接失败", extra={"base_url": self.base_url, "error": str(error)})
        self.raise_connect_error(
            backend_name="Ollama",
            base_url=self.base_url,
            error=error,
            message=f"无法连接到 Ollama 服务 ({self.base_url}).请确保 Ollama 服务正在运行.",
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
        logger.warning("Ollama 请求超时", extra={"timeout": timeout, "error": str(error)})
        self.raise_timeout_error(
            backend_name="Ollama",
            timeout=timeout,
            error=error,
            message="Ollama 请求超时",
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
            data: Ollama API 响应数据
            model: 使用的模型名称
            duration_ms: 调用耗时(毫秒)

        Returns:
            LLMResponse 对象
        """
        # 提取内容
        message = data.get("message", {})
        content = message.get("content", "")

        # 提取 token 使用信息
        # Ollama 返回 prompt_eval_count 和 eval_count
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        total_tokens = prompt_tokens + completion_tokens

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            backend=self.BACKEND_NAME,
        )

    def _build_options(
        self,
        temperature: float,
        max_tokens: int | None = None,
        num_predict: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """
        构建 Ollama options 参数

        Args:
            temperature: 温度参数
            max_tokens: 最大输出 token 数(映射到 num_predict)
            num_predict: Ollama 特有的 num_predict 参数
            **kwargs: 其他 Ollama options 参数

        Returns:
            options 字典,如果没有参数则返回 None
        """
        options: dict[str, Any] = {}

        # 设置温度
        if temperature != 0.7:  # 只有非默认值才设置
            options["temperature"] = temperature

        # num_predict 优先级:显式传入 > max_tokens
        if num_predict is not None:
            options["num_predict"] = num_predict
        elif max_tokens is not None:
            options["num_predict"] = max_tokens

        # 添加其他 Ollama 特有参数
        ollama_options = ["top_k", "top_p", "repeat_penalty", "seed", "num_ctx"]
        for key in ollama_options:
            if key in kwargs and kwargs[key] is not None:
                options[key] = kwargs[key]

        return options if options else None

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
            max_tokens: 最大输出 token 数(映射到 Ollama 的 num_predict)
            **kwargs: Ollama 特有参数:
                - num_predict: 最大生成 token 数
                - timeout: 请求超时时间(秒)
                - top_k, top_p, repeat_penalty, seed, num_ctx 等

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMTimeoutError: 请求超时
        """
        used_model = model or self.default_model

        # 获取超时时间(支持 kwargs 覆盖)
        request_timeout = kwargs.pop("timeout", None) or self.timeout

        # 获取 num_predict(支持 kwargs 传入)
        num_predict = kwargs.pop("num_predict", None)

        # 构建 options
        options = self._build_options(temperature=temperature, max_tokens=max_tokens, num_predict=num_predict, **kwargs)

        # 构建请求
        url = self._build_api_url()
        payload = build_ollama_chat_payload(messages=messages, model=used_model, options=options)

        start_time = time.time()

        try:
            client = get_sync_http_client()
            resp = client.post(url, json=payload, timeout=request_timeout)
            resp.raise_for_status()

            data = parse_ollama_chat_response(resp=resp, model=used_model)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Ollama API 时发生错误: {e!s}", errors={"detail": str(e)}) from e

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
            max_tokens: 最大输出 token 数(映射到 Ollama 的 num_predict)
            **kwargs: Ollama 特有参数:
                - num_predict: 最大生成 token 数
                - timeout: 请求超时时间(秒)
                - top_k, top_p, repeat_penalty, seed, num_ctx 等

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMTimeoutError: 请求超时
        """
        used_model = model or self.default_model

        # 获取超时时间(支持 kwargs 覆盖)
        request_timeout = kwargs.pop("timeout", None) or self.timeout

        # 获取 num_predict(支持 kwargs 传入)
        num_predict = kwargs.pop("num_predict", None)

        # 构建 options
        options = self._build_options(temperature=temperature, max_tokens=max_tokens, num_predict=num_predict, **kwargs)

        # 构建请求
        url = self._build_api_url()
        payload = build_ollama_chat_payload(messages=messages, model=used_model, options=options)

        start_time = time.time()

        try:
            client = get_async_http_client()
            resp = await client.post(url, json=payload, timeout=request_timeout)
            resp.raise_for_status()

            data = parse_ollama_chat_response(resp=resp, model=used_model)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama 异步调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Ollama API 时发生错误: {e!s}", errors={"detail": str(e)}) from e

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
        used_model = model or self.default_model

        request_timeout = kwargs.pop("timeout", None) or self.timeout
        num_predict = kwargs.pop("num_predict", None)
        options = self._build_options(
            temperature=temperature,
            max_tokens=max_tokens,
            num_predict=num_predict,
            **kwargs,
        )

        url = self._build_api_url()
        payload = build_ollama_chat_payload(messages=messages, model=used_model, options=options)
        payload["stream"] = True

        try:
            client = get_sync_http_client()
            with client.stream("POST", url, json=payload, timeout=request_timeout) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = (data.get("message") or {}).get("content") or ""
                    if content:
                        yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)

                    if data.get("done") is True:
                        prompt_tokens = int(data.get("prompt_eval_count") or 0)
                        completion_tokens = int(data.get("eval_count") or 0)
                        yield LLMStreamChunk(
                            usage=LLMUsage(
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=prompt_tokens + completion_tokens,
                            ),
                            model=used_model,
                            backend=self.BACKEND_NAME,
                        )
                        break

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama stream 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(
                message=f"调用 Ollama API 时发生错误: {e!s}",
                errors={"detail": str(e)},
            ) from e

        return

    async def astream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        used_model = model or self.default_model

        request_timeout = kwargs.pop("timeout", None) or self.timeout
        num_predict = kwargs.pop("num_predict", None)
        options = self._build_options(
            temperature=temperature,
            max_tokens=max_tokens,
            num_predict=num_predict,
            **kwargs,
        )

        url = self._build_api_url()
        payload = build_ollama_chat_payload(messages=messages, model=used_model, options=options)
        payload["stream"] = True

        try:
            client = get_async_http_client()
            async with client.stream("POST", url, json=payload, timeout=request_timeout) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = (data.get("message") or {}).get("content") or ""
                    if content:
                        yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)

                    if data.get("done") is True:
                        prompt_tokens = int(data.get("prompt_eval_count") or 0)
                        completion_tokens = int(data.get("eval_count") or 0)
                        yield LLMStreamChunk(
                            usage=LLMUsage(
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=prompt_tokens + completion_tokens,
                            ),
                            model=used_model,
                            backend=self.BACKEND_NAME,
                        )
                        break

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama astream 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(
                message=f"调用 Ollama API 时发生错误: {e!s}",
                errors={"detail": str(e)},
            ) from e

    def chat_with_options(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """
        带 options 参数的聊天接口(兼容原 ollama_client.chat_with_options)

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称,None 时使用默认模型
            options: Ollama 模型选项,如 num_predict, temperature 等
            timeout: 请求超时时间(秒)

        Returns:
            LLMResponse: 统一格式的响应对象

        Example:
            response = backend.chat_with_options(
                messages=[{"role": "user", "content": "你好"}],
                options={"num_predict": 100, "temperature": 0.5},
                timeout=60.0
            )
        """
        used_model = model or self.default_model
        request_timeout = timeout or self.timeout

        url = self._build_api_url()
        payload = build_ollama_chat_payload(messages=messages, model=used_model, options=options)

        start_time = time.time()

        try:
            client = get_sync_http_client()
            resp = client.post(url, json=payload, timeout=request_timeout)
            resp.raise_for_status()

            data = parse_ollama_chat_response(resp=resp, model=used_model)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama chat_with_options 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Ollama API 时发生错误: {e!s}", errors={"detail": str(e)}) from e

        duration_ms = (time.time() - start_time) * 1000

        return self._build_llm_response(data, used_model, duration_ms)

    def get_default_embedding_model(self) -> str:
        return self.default_embedding_model

    def embed_texts(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        if not texts:
            return []

        used_model = (model or self.default_embedding_model).strip()
        request_timeout = kwargs.pop("timeout", None) or self.timeout
        payload = {"model": used_model, "input": texts}
        url = self._build_embed_url()

        try:
            client = get_sync_http_client()
            try:
                resp = client.post(url, json=payload, timeout=request_timeout)
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings")
                if not isinstance(embeddings, list):
                    raise LLMAPIError(
                        message="Ollama embeddings 返回格式异常",
                        errors={"detail": f"invalid response: {data}"},
                    )
                vectors: list[list[float]] = []
                for item in embeddings:
                    if not isinstance(item, list):
                        raise LLMAPIError(
                            message="Ollama embeddings 返回格式异常",
                            errors={"detail": f"invalid embedding item: {item}"},
                        )
                    vectors.append([float(v) for v in item])
                return vectors
            except httpx.HTTPStatusError as e:
                # 兼容旧版 Ollama /api/embeddings 单文本接口
                if e.response.status_code != 404:
                    raise
                vectors: list[list[float]] = []
                legacy_url = self._build_legacy_embed_url()
                for text in texts:
                    legacy_resp = client.post(
                        legacy_url,
                        json={"model": used_model, "prompt": text},
                        timeout=request_timeout,
                    )
                    legacy_resp.raise_for_status()
                    legacy_data = legacy_resp.json()
                    embedding = legacy_data.get("embedding")
                    if not isinstance(embedding, list):
                        raise LLMAPIError(
                            message="Ollama embeddings 返回格式异常",
                            errors={"detail": f"invalid legacy response: {legacy_data}"},
                        )
                    vectors.append([float(v) for v in embedding])
                return vectors
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, used_model)
        except httpx.ConnectError as e:
            self._handle_connect_error(e)
        except httpx.TimeoutException as e:
            self._handle_timeout_error(e, request_timeout)
        except LLMAPIError:
            raise
        except Exception as e:
            logger.warning("Ollama embeddings 调用异常", extra={"error": str(e), "error_type": type(e).__name__})
            raise LLMAPIError(message=f"调用 Ollama embeddings 时发生错误: {e!s}", errors={"detail": str(e)}) from e

    def get_default_model(self) -> str:
        """
        获取默认模型名称

        Returns:
            str: 后端的默认模型名称
        """
        return self.default_model

    _availability_checked: bool = False
    _availability_result: bool | None = None

    def is_available(self) -> bool:
        """
        检查后端是否可用

        Ollama 是本地服务,检查 base_url 配置并通过轻量探针验证连通性.
        探针结果缓存,同一实例内只检查一次.

        Returns:
            bool: True 表示后端可用,False 表示不可用
        """
        if self._availability_checked:
            return self._availability_result is True

        base_url = self.base_url
        if not base_url:
            logger.debug("Ollama 后端不可用:Base URL 未配置")
            self._availability_checked = True
            self._availability_result = False
            return False

        # 轻量探针:请求 /api/tags 验证服务可达
        try:
            client = get_sync_http_client()
            resp = client.get(
                base_url.rstrip("/") + "/api/tags",
                timeout=3.0,
            )
            self._availability_checked = True
            if resp.status_code == 200:
                self._availability_result = True
                return True
            logger.debug(
                "Ollama 探针返回非 200",
                extra={"status_code": resp.status_code, "base_url": base_url},
            )
            self._availability_result = False
            return False
        except Exception as e:
            logger.debug("Ollama 后端不可用:连通性检查失败", extra={"base_url": base_url, "error": str(e)})
            self._availability_checked = True
            self._availability_result = False
            return False


if TYPE_CHECKING:
    _backend: ILLMBackend = OllamaBackend()  # type: ignore[assignment]
