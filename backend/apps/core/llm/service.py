"""
统一 LLM 服务层

提供统一的 LLM 调用接口,支持多后端选择和降级逻辑.

Requirements: 1.2, 1.4, 1.5
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any, ClassVar

from .backends import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk
from .client import LLMClient
from .fallback_policy import LLMFallbackPolicy
from .router import LLMBackendRouter
from .streaming import astream_with_fallback, stream_with_fallback
from .tracking import arecord_llm_call, capture_caller, record_llm_call

logger = logging.getLogger("apps.core.llm.service")


class LLMService:
    """
    统一 LLM 服务

    提供统一的 LLM 调用接口,支持:
    - 多后端选择(openai_compatible/ollama)
    - 自动降级(按优先级尝试可用后端)
    - 统一的响应格式

    Requirements: 1.2, 1.4, 1.5
    """

    # 后端名称常量
    BACKEND_OLLAMA = "ollama"
    BACKEND_OPENAI_COMPATIBLE = "openai_compatible"

    # 默认后端优先级(数字越小优先级越高)
    DEFAULT_PRIORITIES: ClassVar = {
        BACKEND_OPENAI_COMPATIBLE: 1,
        BACKEND_OLLAMA: 2,
    }

    def __init__(
        self,
        backend_configs: dict[str, BackendConfig] | None = None,
        default_backend: str | None = None,
    ) -> None:
        """
        初始化 LLM 服务

        Args:
            backend_configs: 后端配置字典,键为后端名称
            default_backend: 默认后端名称,None 时使用 openai_compatible
        """
        self._backend_configs = backend_configs
        if default_backend:
            self._default_backend = default_backend
        elif backend_configs:
            # 从已有配置中找优先级最高的启用后端
            enabled = [(name, cfg) for name, cfg in backend_configs.items() if cfg.enabled]
            if enabled:
                enabled.sort(key=lambda x: x[1].priority)
                self._default_backend = enabled[0][0]
            else:
                self._default_backend = self.BACKEND_OPENAI_COMPATIBLE
        else:
            from .config import LLMConfig

            self._default_backend = LLMConfig.get_default_backend()
        self._router = LLMBackendRouter(backend_configs=backend_configs)
        self._fallback_policy = LLMFallbackPolicy(router=self._router)
        self._client = LLMClient(default_backend=self._default_backend)

    @classmethod
    async def create(
        cls,
        backend_configs: dict[str, BackendConfig] | None = None,
        default_backend: str | None = None,
    ) -> "LLMService":
        """异步工厂方法: 在 async 上下文中安全创建 LLMService

        预热 LLMConfig 缓存，避免后续 is_available() 触发 SynchronousOnlyOperation。
        """
        from .config import LLMConfig

        if not default_backend and not backend_configs:
            default_backend = await LLMConfig.get_default_backend_async()

        # 预热缓存：async 获取所有后端配置，写入 _config_cache
        await asyncio.gather(
            LLMConfig.get_openai_compatible_api_key_async(),
            LLMConfig.get_openai_compatible_base_url_async(),
        )

        return cls(backend_configs=backend_configs, default_backend=default_backend)

    def _get_backend_config(self, name: str) -> BackendConfig:
        """获取后端配置"""
        return self._router.get_backend_config(name)

    def _get_backend(self, name: str) -> ILLMBackend:
        """获取后端实例(延迟初始化)"""
        return self._router.get_backend(name)

    def _get_backends_by_priority(self) -> list[tuple[str, ILLMBackend]]:
        """按优先级获取所有后端"""
        return self._router.get_backends_by_priority()

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """简化的补全接口"""
        return self._client.complete(
            fallback_policy=self._fallback_policy,
            prompt=prompt,
            system_prompt=system_prompt,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
            caller=caller if caller is not None else capture_caller(),
            **kwargs,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """聊天接口"""
        return self._client.chat(
            fallback_policy=self._fallback_policy,
            messages=messages,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
            caller=caller if caller is not None else capture_caller(),
            **kwargs,
        )

    async def achat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """异步聊天接口"""
        return await self._client.achat(
            fallback_policy=self._fallback_policy,
            messages=messages,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
            caller=caller if caller is not None else capture_caller(),
            **kwargs,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> Iterator[LLMStreamChunk]:
        caller_name = caller if caller is not None else capture_caller()
        started_at = time.monotonic()
        usage = None
        model_used = model or "-"
        backend_used = backend or "-"
        try:
            for chunk in stream_with_fallback(
                get_backend=self._get_backend,
                get_backends_by_priority=self._get_backends_by_priority,
                backend=backend,
                fallback=fallback,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.model:
                    model_used = chunk.model
                if chunk.backend:
                    backend_used = chunk.backend
                yield chunk
        except GeneratorExit:
            return  # 调用方提前放弃，不记录
        except Exception as error:
            record_llm_call(
                backend=backend_used,
                model=model_used,
                duration_ms=(time.monotonic() - started_at) * 1000,
                success=False,
                caller=caller_name,
                error=error,
            )
            raise
        record_llm_call(
            backend=backend_used,
            model=model_used,
            duration_ms=(time.monotonic() - started_at) * 1000,
            success=True,
            caller=caller_name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    async def astream(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        caller_name = caller if caller is not None else capture_caller()
        started_at = time.monotonic()
        usage = None
        model_used = model or "-"
        backend_used = backend or "-"
        try:
            async for chunk in astream_with_fallback(
                get_backend=self._get_backend,
                get_backends_by_priority=self._get_backends_by_priority,
                backend=backend,
                fallback=fallback,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.model:
                    model_used = chunk.model
                if chunk.backend:
                    backend_used = chunk.backend
                yield chunk
        except GeneratorExit:
            return  # 调用方提前放弃，不记录
        except Exception as error:
            await arecord_llm_call(
                backend=backend_used,
                model=model_used,
                duration_ms=(time.monotonic() - started_at) * 1000,
                success=False,
                caller=caller_name,
                error=error,
            )
            raise
        await arecord_llm_call(
            backend=backend_used,
            model=model_used,
            duration_ms=(time.monotonic() - started_at) * 1000,
            success=True,
            caller=caller_name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    def embed_texts(
        self,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        return self._client.embed_texts(
            fallback_policy=self._fallback_policy,
            texts=texts,
            backend=backend,
            model=model,
            fallback=fallback,
            caller=caller if caller is not None else capture_caller(),
            **kwargs,
        )

    async def aembed_texts(
        self,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        caller: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        return await self._client.aembed_texts(
            fallback_policy=self._fallback_policy,
            texts=texts,
            backend=backend,
            model=model,
            fallback=fallback,
            caller=caller if caller is not None else capture_caller(),
            **kwargs,
        )

    def get_backend(self, name: str) -> ILLMBackend:
        """获取指定后端实例"""
        return self._get_backend(name)


# 模块级单例(延迟初始化)
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
