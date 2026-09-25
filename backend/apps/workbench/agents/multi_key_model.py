"""Agent 路径的多 Key 轮询 Model。

背景：``build_model`` 原先只取 ``api_keys[0]`` 单 Key，网关（LiteLLM）的
「每 Key 并发上限」完全用不上——10 个并发请求全部压在同一个 Key 上，
超出上限的部分直接吃 429，只能靠重试拉长尾延迟。

本模块把服务路径的 :class:`~apps.core.llm.key_pool.KeyPool` 复用到 Agent 路径：
每个 Key 各建一个 ``OpenAIChatModel``，按请求从池中取槽位轮询，失败自动换 Key。
取槽位发生在 ``request`` / ``request_stream`` 层，因此 Key 的占用时长与
「一次模型调用」严格对齐——流式响应会一直持有到流关闭为止。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, NoReturn

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.llm.exceptions import LLMAPIError
from apps.core.llm.key_pool import KeyPool

logger = logging.getLogger(__name__)


class MultiKeyOpenAIModel(WrapperModel):
    """在多个「单 Key」模型之间按 Key 池轮询，失败自动切换到下一个 Key。

    ``WrapperModel`` 会把 ``model_name`` / ``system`` / ``profile`` 等元信息转发给
    第一个底层模型，因此对 pydantic-ai 的其余部分完全透明。
    """

    def __init__(self, models: list[Model], pool: KeyPool, model_name: str) -> None:
        """初始化。

        Args:
            models: 与 ``pool.keys`` 一一对应的单 Key 模型列表（下标即 Key 下标）。
            pool: 该平台共享的 Key 池，负责轮询与每 Key 并发记账。
            model_name: 用于按模型过滤候选 Key（白名单）以及失败冷却记账。
        """
        if not models:
            raise ValueError("MultiKeyOpenAIModel 至少需要一个底层模型")
        super().__init__(models[0])
        self._models = list(models)
        self._pool = pool
        self._model_name = model_name

    # ── 内部 ────────────────────────────────────────────────────────────────

    @property
    def key_count(self) -> int:
        """底层单 Key 模型数量，即本模型可轮询的 Key 数（供日志与监控观察）。"""
        return len(self._models)

    def _raise_no_key(self, last_error: Exception | None) -> NoReturn:
        """无可用 Key：优先抛出最后一次真实错误，否则给出可读的兜底错误。"""
        if last_error is not None:
            raise last_error
        raise LLMAPIError(
            message=f"模型 {self._model_name} 没有可用的 API Key（未授权或全部处于冷却期）",
            errors={"detail": "no available key", "model": self._model_name},
        )

    def _log_switch(self, idx: int, error: Exception) -> None:
        logger.warning(
            "Agent 路径 Key 调用失败，切换下一个 Key",
            extra={"model": self._model_name, "key_index": idx, "error_type": type(error).__name__},
        )

    # ── Model 协议 ──────────────────────────────────────────────────────────

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """非流式调用：取槽位 → 调用 → 成功归还 / 失败换下一个 Key。"""
        last_error: Exception | None = None
        for _ in range(max(1, len(self._models))):
            idx = self._pool.acquire(self._model_name)
            if idx is None:
                break
            try:
                result = await self._models[idx].request(messages, model_settings, model_request_parameters)
            except Exception as error:
                self._pool.release(idx, success=False, model=self._model_name)
                last_error = error
                self._log_switch(idx, error)
                continue
            self._pool.release(idx, success=True, model=self._model_name)
            return result
        self._raise_no_key(last_error)

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        """流式调用。

        与 ``request`` 的差别在于「建立连接」与「消费响应」是两个阶段，必须分开处理：

        - **建立失败**（HTTP 层面就没成功，如 429/401）→ 记一次失败并换 Key 重试，
          此时尚未产出任何内容，重试对调用方无感；
        - **建立成功** → Key 一直持有到流关闭。消费过程中的异常（含工具执行报错、
          调用方提前 break）不再换 Key，否则会把已经吐出的部分内容重复一遍。
        """
        last_error: Exception | None = None
        for _ in range(max(1, len(self._models))):
            idx = self._pool.acquire(self._model_name)
            if idx is None:
                break
            stream_cm = self._models[idx].request_stream(
                messages, model_settings, model_request_parameters, run_context
            )
            try:
                stream = await stream_cm.__aenter__()
            except Exception as error:
                self._pool.release(idx, success=False, model=self._model_name)
                last_error = error
                self._log_switch(idx, error)
                continue

            healthy = False
            try:
                yield stream
                healthy = True
            except (GeneratorExit, asyncio.CancelledError):
                # 调用方提前关闭（客户端断开 / 任务取消）：不是 Key 的故障，不记冷却
                healthy = True
                raise
            finally:
                try:
                    await stream_cm.__aexit__(None, None, None)
                finally:
                    self._pool.release(idx, success=healthy, model=self._model_name)
            return
        self._raise_no_key(last_error)


# ─── 进程级 Key 池 ───────────────────────────────────────────────────────────

_pool_cache: dict[tuple[Any, ...], KeyPool] = {}
_pool_cache_lock = threading.Lock()

#: 平台未声明「每 Key 并发上限」时，Agent 路径沿用的默认全局并发
DEFAULT_AGENT_CONCURRENCY = 10


def shared_key_pool(provider: OpenAIProviderConfig) -> KeyPool:
    """返回该平台在进程内共享的 Key 池；Key 列表 / 上限 / 白名单变化时重建。

    ``build_model`` 是**每次请求**都会调用的，若每次都新建池，每 Key 并发上限
    会随请求数被无限放大，等于没有限制。因此按配置内容寻址复用。
    """
    scope_key = tuple(sorted((key, tuple(models)) for key, models in provider.key_model_scopes.items()))
    cache_key = (provider.name, tuple(provider.api_keys), int(provider.concurrency_per_key or 0), scope_key)
    with _pool_cache_lock:
        pool = _pool_cache.get(cache_key)
        if pool is None:
            # 同平台的旧配置池已失效，顺手清掉，避免长期堆积
            for stale in [k for k in _pool_cache if k[0] == provider.name]:
                del _pool_cache[stale]
            pool = KeyPool(provider.api_keys, provider.concurrency_per_key, provider.key_model_scopes)
            _pool_cache[cache_key] = pool
        return pool


def agent_concurrency_capacity(provider: OpenAIProviderConfig | None) -> int:
    """Agent 路径的全局并发上限：Key 数 × 每 Key 上限。

    取该值作为全局闸门，是因为再往上加并发只会触发 ``KeyPool`` 的「超限兜底」，
    用延迟换成功率；卡在容量点上排队反而是更优解。

    平台未配置 Key 或上限为 0（不限制）时返回 ``DEFAULT_AGENT_CONCURRENCY``。
    """
    if provider is None or not provider.api_keys:
        return DEFAULT_AGENT_CONCURRENCY
    per_key = int(provider.concurrency_per_key or 0)
    if per_key <= 0:
        return DEFAULT_AGENT_CONCURRENCY
    return max(1, per_key * len(provider.api_keys))
