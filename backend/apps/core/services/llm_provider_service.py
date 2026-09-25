"""LLM 平台（供应商）配置服务。

从 LLMProvider 模型读取启用的 OpenAI-compatible 平台配置，带 TTL 缓存。
同步/异步双通道，供 LLMConfig 与后端使用。
另提供「拉取远端模型列表」能力，供 Admin 按 Key 探测网关的授权模型。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx

from apps.core.llm.backends.base import OpenAIProviderConfig

logger = logging.getLogger("apps.core.services.llm_provider")


@dataclass
class RemoteKeyModels:
    """单个 Key 拉取远端模型列表的结果。

    Attributes:
        index: Key 序号（从 1 开始，仅用于展示，不泄露 Key 内容）。
        ok: 该 Key 的请求是否成功。
        models: 该 Key 被授权访问的模型列表。
        error: 失败原因摘要（不含 Key 明文）。
    """

    index: int
    ok: bool
    models: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class RemoteModelList:
    """远端模型列表拉取结果。

    Attributes:
        url: 实际请求的地址。
        per_key: 每个 Key 的单独结果。
        models: 所有成功 Key 的模型并集（保序），含向量/重排等**非对话模型**。
        common_models: 所有成功 Key 的模型交集——即「任意 Key 都能跑」的模型。
        chat_models: 经探测确认支持 ``/chat/completions`` 的模型（未探测时为空）。
    """

    url: str = ""
    per_key: list[RemoteKeyModels] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    common_models: list[str] = field(default_factory=list)
    chat_models: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """是否存在至少一个拉取成功的 Key。"""
        return any(item.ok for item in self.per_key)


def _extract_model_ids(payload: Any) -> list[str]:
    """从 OpenAI-compatible ``/models`` 响应中提取模型 id（去重保序）。

    兼容 ``{"data": [{"id": "..."}]}`` 与 ``{"data": ["..."]}`` 两种形态。
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
        elif isinstance(item, str):
            model_id = item.strip()
        else:
            model_id = ""
        if model_id and model_id not in ids:
            ids.append(model_id)
    return ids


class LLMProviderService:
    """LLM 平台配置服务（进程内 TTL 缓存）。"""

    _CACHE_TTL_SECONDS: ClassVar[float] = 300.0
    _MODELS_TIMEOUT_SECONDS: ClassVar[float] = 15.0
    _CHAT_PROBE_TIMEOUT_SECONDS: ClassVar[float] = 10.0
    _cache: ClassVar[tuple[list[OpenAIProviderConfig], float] | None] = None

    @classmethod
    def invalidate_cache(cls) -> None:
        """清空平台配置缓存（Admin 保存/删除后调用，使改动立即生效）。"""
        cls._cache = None

    @classmethod
    def get_providers(cls) -> list[OpenAIProviderConfig]:
        """同步读取启用的平台配置列表（带缓存）。"""
        cached = cls._cache
        if cached is not None:
            value, cached_at = cached
            if time.monotonic() - cached_at <= cls._CACHE_TTL_SECONDS:
                return value

        try:
            providers = cls._load_from_db()
        except Exception:
            logger.warning("[LLMProviderService] 读取平台配置失败", exc_info=True)
            providers = []
        cls._cache = (providers, time.monotonic())
        return providers

    @classmethod
    async def aget_providers(cls) -> list[OpenAIProviderConfig]:
        """异步读取启用的平台配置列表（带缓存）。"""
        cached = cls._cache
        if cached is not None:
            value, cached_at = cached
            if time.monotonic() - cached_at <= cls._CACHE_TTL_SECONDS:
                return value

        from asgiref.sync import sync_to_async

        try:
            providers = await sync_to_async(cls._load_from_db)()
        except Exception:
            logger.warning("[LLMProviderService] 异步读取平台配置失败", exc_info=True)
            providers = []
        cls._cache = (providers, time.monotonic())
        return providers

    @classmethod
    def _load_from_db(cls) -> list[OpenAIProviderConfig]:
        try:
            from apps.core.models import LLMProvider

            rows = list(LLMProvider.objects.filter(enabled=True))
        except Exception:
            logger.warning("[LLMProviderService] 读取平台配置失败", exc_info=True)
            return []

        providers: list[OpenAIProviderConfig] = []
        for row in rows:
            entries = row.parsed_key_entries()
            providers.append(
                OpenAIProviderConfig(
                    name=str(row.name),
                    base_url=(row.base_url or "").strip(),
                    api_keys=[key for key, _ in entries],
                    key_model_scopes={key: models for key, models in entries if models},
                    default_model=(row.default_model or "").strip(),
                    extra_models=row.parsed_models(),
                    embedding_model=(row.embedding_model or "").strip(),
                    timeout=int(row.timeout or 120),
                    concurrency_per_key=int(row.concurrency_per_key or 0),
                    priority=int(row.priority or 10),
                    enabled=bool(row.enabled),
                )
            )
        providers.sort(key=lambda p: (p.priority, p.name))
        return providers

    # ── 远端模型列表 ─────────────────────────────────────────────────────────

    @classmethod
    def fetch_remote_models(
        cls,
        base_url: str,
        api_keys: list[str] | None = None,
        timeout: float | None = None,
        *,
        probe_chat: bool = True,
    ) -> RemoteModelList:
        """拉取 OpenAI-compatible 网关的模型列表，**逐个 Key** 请求后聚合。

        网关（如 LiteLLM）的 ``/v1/models`` 通常按 Key 返回其授权模型白名单，
        因此逐 Key 请求才能暴露「哪些 Key 支持哪些模型」。未配置 Key 时按匿名
        请求一次（兼容本地免鉴权 vLLM）。

        该接口会把**非对话模型**（向量、重排、OCR 等）一并列出，因此默认再用一次
        最小 ``/chat/completions`` 请求逐个探测对话能力，结果放在 ``chat_models``；
        只有 ``chat_models`` 才适合写入平台的「模型列表」（`extra_models`）。

        Args:
            base_url: 平台 API 地址，需已包含版本前缀（如 ``http://host:4000/v1``）。
            api_keys: 待探测的 Key 列表；为空时匿名请求一次。
            timeout: 单次请求超时秒数，默认 15 秒。
            probe_chat: 是否探测对话能力（每个模型额外一次最小请求）。

        Returns:
            :class:`RemoteModelList`，含每 Key 结果、并集、交集与对话模型。
        """
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return RemoteModelList()

        url = f"{normalized}/models"
        request_timeout = float(timeout or cls._MODELS_TIMEOUT_SECONDS)
        targets: list[str | None] = [key for key in (api_keys or []) if key] or [None]

        per_key = [
            cls._fetch_models_once(url, api_key=key, timeout=request_timeout, index=index)
            for index, key in enumerate(targets, 1)
        ]
        union = cls._union_models(per_key)
        return RemoteModelList(
            url=url,
            per_key=per_key,
            models=union,
            common_models=cls._common_models(per_key),
            chat_models=cls._probe_chat_models(normalized, per_key, targets, union) if probe_chat else [],
        )

    @classmethod
    def _fetch_models_once(cls, url: str, *, api_key: str | None, timeout: float, index: int) -> RemoteKeyModels:
        """请求一次 ``/models`` 并解析结果；失败原因只保留状态码或异常类型。"""
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            response = httpx.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            return RemoteKeyModels(index=index, ok=False, error=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            logger.warning("[LLMProviderService] 拉取远端模型列表失败", extra={"url": url}, exc_info=True)
            return RemoteKeyModels(index=index, ok=False, error=type(exc).__name__)
        return RemoteKeyModels(index=index, ok=True, models=_extract_model_ids(payload))

    @classmethod
    def _probe_chat_models(
        cls,
        base_url: str,
        per_key: list[RemoteKeyModels],
        targets: list[str | None],
        models: list[str],
    ) -> list[str]:
        """逐个模型探测 ``/chat/completions`` 能力，返回确认可用的模型（保序）。

        无法判定（网络异常 / 超时 / 5xx）的模型按「支持」处理，避免探测抖动把可用
        模型漏掉；只有明确的 4xx 才判定为不支持。
        """
        owner: dict[str, str | None] = {}
        for item, api_key in zip(per_key, targets, strict=False):
            if not item.ok:
                continue
            for model_id in item.models:
                owner.setdefault(model_id, api_key)

        probe_timeout = min(float(cls._MODELS_TIMEOUT_SECONDS), cls._CHAT_PROBE_TIMEOUT_SECONDS)
        return [
            model_id
            for model_id in models
            if cls._probe_chat_once(base_url, model_id, owner.get(model_id), probe_timeout) is not False
        ]

    @classmethod
    def _probe_chat_once(cls, base_url: str, model: str, api_key: str | None, timeout: float) -> bool | None:
        """探测单个模型是否支持对话。

        Returns:
            True 支持；False 明确不支持（4xx）；None 无法判定。
        """
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        try:
            response = httpx.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        except Exception:
            logger.debug("[LLMProviderService] 对话能力探测未完成", extra={"model": model}, exc_info=True)
            return None
        if response.status_code == 200:
            return True
        if 400 <= response.status_code < 500:
            return False
        return None

    @classmethod
    def _union_models(cls, per_key: list[RemoteKeyModels]) -> list[str]:
        """所有成功 Key 的模型并集（保序）。"""
        union: list[str] = []
        for result in per_key:
            if not result.ok:
                continue
            for model_id in result.models:
                if model_id not in union:
                    union.append(model_id)
        return union

    @classmethod
    def _common_models(cls, per_key: list[RemoteKeyModels]) -> list[str]:
        """所有成功 Key 都能访问的模型（交集，保序）。"""
        ok_sets = [set(result.models) for result in per_key if result.ok]
        if not ok_sets:
            return []
        return [model_id for model_id in cls._union_models(per_key) if all(model_id in s for s in ok_sets)]

    @classmethod
    def initialize_default(cls) -> tuple[int, int]:
        """初始化基础 AI 平台数据（律所 kimi 默认平台模板）。

        幂等：仅当表为空时写入一条基础平台；已存在任何平台则跳过。
        返回 (created, skipped)。
        """
        from apps.core.llm.config import LLMConfig
        from apps.core.models import LLMProvider

        if LLMProvider.objects.exists():
            return (0, 1)
        LLMProvider.objects.create(
            name="律所 kimi",
            base_url=LLMConfig.DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
            api_keys="",
            default_model=LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL,
            embedding_model="",
            priority=10,
            concurrency_per_key=3,
            enabled=True,
        )
        cls.invalidate_cache()
        return (1, 0)
