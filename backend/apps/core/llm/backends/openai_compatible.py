"""OpenAI-compatible LLM backend."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, NoReturn

import httpx2 as httpx
import openai

from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMError, LLMNetworkError, LLMTimeoutError

from .base import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk, LLMUsage, OpenAIProviderConfig

logger = logging.getLogger("apps.core.llm.backends.openai_compatible")

_LOG_CONTENT_PREVIEW_LIMIT = 80


def _content_preview(content: str, limit: int = _LOG_CONTENT_PREVIEW_LIMIT) -> str:
    """响应内容日志预览：截断，避免把全量（可能含敏感法律文书）内容写进日志。"""
    if len(content) <= limit:
        return content
    return f"{content[:limit]}…(共{len(content)}字)"


def _pick_provider(providers: list[OpenAIProviderConfig], model: str) -> OpenAIProviderConfig | None:
    """按模型名匹配平台；未匹配时返回优先级最高的启用平台。"""
    enabled = [p for p in providers if p.enabled]
    if not enabled:
        return None
    used = (model or "").strip()
    if used:
        for p in enabled:
            if used in p.all_models:
                return p
    return min(enabled, key=lambda p: (p.priority, p.name))


class _KeyPool:
    """单平台多 Key 槽位管理：轮询分配、每 Key 并发上限、失败冷却。

    - 并发上限为 0 表示不限制；
    - 全部 Key 处于并发上限时超限使用（保证请求可用）；
    - 失败后的 Key 进入 30 秒冷却，避免反复打到失效 Key。
    """

    COOLDOWN_SECONDS = 30.0

    def __init__(self, keys: list[str], concurrency_per_key: int = 0) -> None:
        self.keys = list(keys)
        self.limit = max(0, int(concurrency_per_key or 0))
        self._active = [0] * len(self.keys)
        self._failed_until = [0.0] * len(self.keys)
        self._cursor = 0
        self._lock = threading.Lock()

    def acquire(self) -> int | None:
        """选中一个可用 Key 下标并占用；全部 Key 冷却中返回 None。"""
        with self._lock:
            n = len(self.keys)
            if n == 0:
                return None
            now = time.monotonic()
            for _ in range(n):
                idx = self._cursor % n
                self._cursor += 1
                if self._failed_until[idx] > now:
                    continue
                if self.limit and self._active[idx] >= self.limit:
                    continue
                self._active[idx] += 1
                return idx
            # 全部处于并发上限：超限使用下一个未冷却的 Key，保证请求可用
            for _ in range(n):
                idx = self._cursor % n
                self._cursor += 1
                if self._failed_until[idx] <= now:
                    self._active[idx] += 1
                    return idx
            return None

    def release(self, idx: int, *, success: bool) -> None:
        with self._lock:
            if 0 <= idx < len(self._active):
                self._active[idx] = max(0, self._active[idx] - 1)
                if not success:
                    self._failed_until[idx] = time.monotonic() + self.COOLDOWN_SECONDS


class OpenAICompatibleBackend:
    """Generic backend for OpenAI-compatible providers (Moonshot/Kimi/DeepSeek etc.).

    支持多平台（LLMProvider）路由：按模型名匹配平台，匹配失败时使用优先级最高的平台；
    同一平台多 Key 轮询 + 每 Key 并发上限 + 失败切换。
    """

    BACKEND_NAME = "openai_compatible"

    def __init__(self, config: BackendConfig | None = None) -> None:
        self._config = config
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._default_model: str | None = None
        self._timeout: int | None = None
        # 客户端缓存：sync 按 (api_key, base_url, timeout) 复用；
        # async 按 (事件循环, api_key, base_url, timeout) 复用
        self._sync_clients: dict[tuple[str, str, float], openai.OpenAI] = {}
        self._async_clients: dict[tuple[int, str, str, float], openai.AsyncOpenAI] = {}
        self._key_pools: dict[str, _KeyPool] = {}

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

    # ── 平台路由 ─────────────────────────────────────────────────────────────

    def _providers_from_config(self) -> list[OpenAIProviderConfig]:
        if self._config and self._config.providers:
            return list(self._config.providers)
        return []

    def _resolve_provider(self, model: str | None) -> OpenAIProviderConfig | None:
        providers = self._providers_from_config()
        if not providers:
            from apps.core.services.llm_provider_service import LLMProviderService

            providers = LLMProviderService.get_providers()
        return _pick_provider(providers, model or "")

    async def _aresolve_provider(self, model: str | None) -> OpenAIProviderConfig | None:
        providers = self._providers_from_config()
        if not providers:
            from apps.core.services.llm_provider_service import LLMProviderService

            providers = await LLMProviderService.aget_providers()
        return _pick_provider(providers, model or "")

    def _endpoint_for(self, provider: OpenAIProviderConfig | None) -> tuple[str, str]:
        """返回 (base_url, api_key)；平台未配置 Key（本地 vLLM 等）时返回空 Key。"""
        if provider is not None:
            return provider.base_url, ""
        return self.base_url, self.api_key

    def _key_pool(self, provider: OpenAIProviderConfig) -> _KeyPool:
        limit = provider.concurrency_per_key or 0
        pool = self._key_pools.get(provider.name)
        if pool is None or pool.keys != provider.api_keys or pool.limit != limit:
            pool = _KeyPool(provider.api_keys, limit)
            self._key_pools[provider.name] = pool
        return pool

    def _raise_no_key_available(self, last_error: Exception | None, timeout: float, base_url: str) -> NoReturn:
        if last_error is None:
            raise LLMAPIError(
                message="LLM 调用失败：该平台全部 API Key 均不可用",
                errors={"detail": "no available key"},
            )
        if isinstance(last_error, LLMError):
            raise last_error
        self._raise_mapped_error(last_error, timeout, base_url)

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

    def _build_payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        extra = self._build_extra_body(model)
        if extra:
            payload["extra_body"] = extra
        return payload

    def _build_response(self, response: Any, used_model: str, start_time: float) -> LLMResponse:
        duration_ms = (time.time() - start_time) * 1000
        usage = self._extract_usage(getattr(response, "usage", None))
        content = self._extract_content(response)
        # 响应内容可能包含敏感法律文书，只记截断预览且降为 debug
        logger.debug(
            "OpenAICompatible.chat 响应: model=%s, content=%s, choices=%s, usage=%s",
            used_model,
            _content_preview(content),
            len(getattr(response, "choices", None) or []),
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

    # ── 客户端构建（缓存复用，避免每次调用重建连接池） ───────────────────────

    @staticmethod
    def _ssl_verify() -> bool:
        # SSL 验证可通过环境变量 LLM_SSL_VERIFY=false 关闭（仅用于特殊 CDN/代理环境）
        import os

        return os.environ.get("LLM_SSL_VERIFY", "true").lower() not in ("false", "0", "no")

    def _build_sync_client(self, api_key: str, base_url: str, timeout_seconds: float) -> openai.OpenAI:
        timeout_val = float(timeout_seconds)
        cache_key = (api_key, base_url, timeout_val)
        cached = self._sync_clients.get(cache_key)
        if cached is not None:
            return cached
        transport = httpx.HTTPTransport(verify=self._ssl_verify())
        http_client = httpx.Client(transport=transport, timeout=timeout_val)
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_val,
            http_client=http_client,
        )
        # 只保留同 base_url 的客户端（同一平台多 Key 轮询共享连接池，切换平台才重建）
        self._sync_clients = {k: v for k, v in self._sync_clients.items() if k[1] == base_url}
        self._sync_clients[cache_key] = client
        return client

    async def _build_async_client(self, api_key: str, base_url: str, timeout_seconds: float) -> openai.AsyncOpenAI:
        import asyncio

        timeout_val = float(timeout_seconds)
        loop_id = id(asyncio.get_running_loop())
        cache_key = (loop_id, api_key, base_url, timeout_val)
        cached = self._async_clients.get(cache_key)
        if cached is not None:
            return cached
        transport = httpx.AsyncHTTPTransport(verify=self._ssl_verify())
        http_async_client = httpx.AsyncClient(transport=transport, timeout=timeout_val)
        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_val,
            http_client=http_async_client,
        )
        # 只保留当前事件循环、且同 base_url 的客户端；旧循环已结束，其连接随循环销毁
        self._async_clients = {k: v for k, v in self._async_clients.items() if k[0] == loop_id and k[2] == base_url}
        self._async_clients[cache_key] = client
        return client

    def close_clients(self) -> None:
        """关闭缓存的同步客户端（进程退出或测试清理时调用）。"""
        for client in self._sync_clients.values():
            try:
                client.close()
            except Exception:
                logger.debug("关闭同步 LLM 客户端失败", exc_info=True)
        self._sync_clients.clear()

    async def aclose_clients(self) -> None:
        """关闭缓存中的全部异步客户端（旧事件循环的客户端不保证可关闭，尽力而为）。"""
        for client in self._async_clients.values():
            try:
                await client.close()
            except Exception:
                logger.debug("关闭异步 LLM 客户端失败", exc_info=True)
        self._async_clients.clear()

    # ── 错误映射 ─────────────────────────────────────────────────────────────

    def _raise_mapped_error(self, error: Exception, timeout_seconds: float, base_url: str) -> NoReturn:
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
        provider = self._resolve_provider(used_model)
        request_timeout = float(kwargs.pop("timeout_seconds", provider.timeout if provider else self.timeout))
        payload = self._build_payload(used_model, messages, temperature, max_tokens)

        base_url, api_key = self._endpoint_for(provider)
        if provider is None or not provider.api_keys:
            return self._chat_sync_once(api_key, base_url, request_timeout, payload, used_model)

        pool = self._key_pool(provider)
        last_error: Exception | None = None
        for _ in range(max(1, len(pool.keys))):
            idx = pool.acquire()
            if idx is None:
                break
            try:
                result = self._chat_sync_once(pool.keys[idx], provider.base_url, request_timeout, payload, used_model)
                pool.release(idx, success=True)
                return result
            except Exception as error:
                pool.release(idx, success=False)
                last_error = error
                logger.warning(
                    "OpenAI-compatible Key 调用失败，切换下一个 Key",
                    extra={"provider": provider.name, "error_type": type(error).__name__},
                )
        self._raise_no_key_available(last_error, request_timeout, provider.base_url)

    def _chat_sync_once(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        payload: dict[str, Any],
        used_model: str,
    ) -> LLMResponse:
        start_time = time.time()
        client = self._build_sync_client(api_key=api_key, base_url=base_url, timeout_seconds=timeout)
        try:
            response = client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, timeout, base_url)
        return self._build_response(response, used_model, start_time)

    async def _chat_async_once(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        payload: dict[str, Any],
        used_model: str,
    ) -> LLMResponse:
        start_time = time.time()
        client = await self._build_async_client(api_key=api_key, base_url=base_url, timeout_seconds=timeout)
        try:
            response = await client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, timeout, base_url)
        return self._build_response(response, used_model, start_time)

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
        provider = await self._aresolve_provider(used_model)
        if provider is not None:
            default_timeout = float(provider.timeout)
        elif self._config and self._config.timeout:
            default_timeout = float(self._config.timeout)
        else:
            default_timeout = await LLMConfig.get_openai_compatible_timeout_async()
        request_timeout = float(kwargs.pop("timeout_seconds", default_timeout))
        payload = self._build_payload(used_model, messages, temperature, max_tokens)

        base_url, api_key = self._endpoint_for(provider)
        if provider is None or not provider.api_keys:
            return await self._chat_async_once(api_key, base_url, request_timeout, payload, used_model)

        pool = self._key_pool(provider)
        last_error: Exception | None = None
        for _ in range(max(1, len(pool.keys))):
            idx = pool.acquire()
            if idx is None:
                break
            try:
                result = await self._chat_async_once(
                    pool.keys[idx], provider.base_url, request_timeout, payload, used_model
                )
                pool.release(idx, success=True)
                return result
            except Exception as error:
                pool.release(idx, success=False)
                last_error = error
                logger.warning(
                    "OpenAI-compatible Key 调用失败，切换下一个 Key",
                    extra={"provider": provider.name, "error_type": type(error).__name__},
                )
        self._raise_no_key_available(last_error, request_timeout, provider.base_url)

    def _create_sync_stream(self, api_key: str, base_url: str, timeout: float, payload: dict[str, Any]) -> Any:
        client = self._build_sync_client(api_key=api_key, base_url=base_url, timeout_seconds=timeout)
        try:
            return client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, timeout, base_url)

    async def _create_async_stream(self, api_key: str, base_url: str, timeout: float, payload: dict[str, Any]) -> Any:
        client = await self._build_async_client(api_key=api_key, base_url=base_url, timeout_seconds=timeout)
        try:
            return await client.chat.completions.create(**payload)
        except Exception as error:
            self._raise_mapped_error(error, timeout, base_url)

    def _iter_stream(self, stream: Any, used_model: str) -> Iterator[LLMStreamChunk]:
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", "") if delta is not None else ""
                if content:
                    yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                yield LLMStreamChunk(usage=self._extract_usage(usage), model=used_model, backend=self.BACKEND_NAME)

    async def _aiter_stream(self, stream: Any, used_model: str) -> AsyncIterator[LLMStreamChunk]:
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", "") if delta is not None else ""
                if content:
                    yield LLMStreamChunk(content=content, model=used_model, backend=self.BACKEND_NAME)
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                yield LLMStreamChunk(usage=self._extract_usage(usage), model=used_model, backend=self.BACKEND_NAME)

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[LLMStreamChunk]:
        used_model = model or self.default_model
        provider = self._resolve_provider(used_model)
        request_timeout = float(kwargs.pop("timeout_seconds", provider.timeout if provider else self.timeout))
        payload = self._build_payload(used_model, messages, temperature, max_tokens, stream=True)

        base_url, api_key = self._endpoint_for(provider)
        if provider is None or not provider.api_keys:
            stream_obj = self._create_sync_stream(api_key, base_url, request_timeout, payload)
            try:
                yield from self._iter_stream(stream_obj, used_model)
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, base_url)
            return

        pool = self._key_pool(provider)
        last_error: Exception | None = None
        for _ in range(max(1, len(pool.keys))):
            idx = pool.acquire()
            if idx is None:
                break
            try:
                stream_obj = self._create_sync_stream(pool.keys[idx], provider.base_url, request_timeout, payload)
            except Exception as error:
                pool.release(idx, success=False)
                last_error = error
                continue
            ok = False
            try:
                yield from self._iter_stream(stream_obj, used_model)
                ok = True
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, provider.base_url)
            finally:
                pool.release(idx, success=ok)
            return
        self._raise_no_key_available(last_error, request_timeout, provider.base_url)

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
        provider = await self._aresolve_provider(used_model)
        if provider is not None:
            default_timeout = float(provider.timeout)
        elif self._config and self._config.timeout:
            default_timeout = float(self._config.timeout)
        else:
            default_timeout = await LLMConfig.get_openai_compatible_timeout_async()
        request_timeout = float(kwargs.pop("timeout_seconds", default_timeout))
        payload = self._build_payload(used_model, messages, temperature, max_tokens, stream=True)

        base_url, api_key = self._endpoint_for(provider)
        if provider is None or not provider.api_keys:
            stream_obj = await self._create_async_stream(api_key, base_url, request_timeout, payload)
            try:
                async for chunk in self._aiter_stream(stream_obj, used_model):
                    yield chunk
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, base_url)
            return

        pool = self._key_pool(provider)
        last_error: Exception | None = None
        for _ in range(max(1, len(pool.keys))):
            idx = pool.acquire()
            if idx is None:
                break
            try:
                stream_obj = await self._create_async_stream(
                    pool.keys[idx], provider.base_url, request_timeout, payload
                )
            except Exception as error:
                pool.release(idx, success=False)
                last_error = error
                continue
            ok = False
            try:
                async for chunk in self._aiter_stream(stream_obj, used_model):
                    yield chunk
                ok = True
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, provider.base_url)
            finally:
                pool.release(idx, success=ok)
            return
        self._raise_no_key_available(last_error, request_timeout, provider.base_url)

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
        provider = self._resolve_provider(None)
        if provider is not None:
            base_url = provider.base_url
            used_model = (model or "").strip() or (provider.embedding_model or provider.default_model or "").strip()
            default_timeout = float(provider.timeout)
        else:
            base_url = self.base_url
            used_model = self._resolve_embedding_model(model)
            default_timeout = float(self.timeout)
        request_timeout = float(kwargs.pop("timeout_seconds", default_timeout))

        def _embed_once(api_key: str) -> list[list[float]]:
            client = self._build_sync_client(api_key=api_key, base_url=base_url, timeout_seconds=request_timeout)
            try:
                response = client.embeddings.create(model=used_model, input=texts)
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, base_url)
            vectors: list[list[float]] = []
            for item in getattr(response, "data", None) or []:
                vectors.append([float(v) for v in (getattr(item, "embedding", None) or [])])
            return vectors

        if provider is not None and provider.api_keys:
            pool = self._key_pool(provider)
            last_error: Exception | None = None
            for _ in range(max(1, len(pool.keys))):
                idx = pool.acquire()
                if idx is None:
                    break
                try:
                    result = _embed_once(pool.keys[idx])
                    pool.release(idx, success=True)
                    return result
                except Exception as error:
                    pool.release(idx, success=False)
                    last_error = error
            self._raise_no_key_available(last_error, request_timeout, base_url)
        return _embed_once("")

    async def aembed_texts(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """异步向量化文本列表。"""
        if not texts:
            return []
        provider = await self._aresolve_provider(None)
        if provider is not None:
            base_url = provider.base_url
            used_model = (model or "").strip() or (provider.embedding_model or provider.default_model or "").strip()
            default_timeout = float(provider.timeout)
        else:
            base_url = self.base_url
            used_model = self._resolve_embedding_model(model)
            default_timeout = float(self.timeout)
        request_timeout = float(kwargs.pop("timeout_seconds", default_timeout))

        async def _aembed_once(api_key: str) -> list[list[float]]:
            client = await self._build_async_client(api_key=api_key, base_url=base_url, timeout_seconds=request_timeout)
            try:
                response = await client.embeddings.create(model=used_model, input=texts)
            except Exception as error:
                self._raise_mapped_error(error, request_timeout, base_url)
            vectors: list[list[float]] = []
            for item in getattr(response, "data", None) or []:
                vectors.append([float(v) for v in (getattr(item, "embedding", None) or [])])
            return vectors

        if provider is not None and provider.api_keys:
            pool = self._key_pool(provider)
            last_error: Exception | None = None
            for _ in range(max(1, len(pool.keys))):
                idx = pool.acquire()
                if idx is None:
                    break
                try:
                    result = await _aembed_once(pool.keys[idx])
                    pool.release(idx, success=True)
                    return result
                except Exception as error:
                    pool.release(idx, success=False)
                    last_error = error
            self._raise_no_key_available(last_error, request_timeout, base_url)
        return await _aembed_once("")

    def is_available(self) -> bool:
        if self._config and not self._config.enabled:
            logger.debug("OpenAI-compatible 后端不可用:已在配置中禁用")
            return False
        providers = self._providers_from_config()
        if not providers:
            try:
                from apps.core.services.llm_provider_service import LLMProviderService

                providers = LLMProviderService.get_providers()
            except Exception:
                providers = []
        if any(p.enabled and p.base_url for p in providers):
            return True
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
