from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.core.cache import cache

from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

CACHE_KEY = "siliconflow_model_list"
CACHE_KEY_STATUS = "siliconflow_model_list_status"
DEFAULT_CACHE_TTL = 3600

# 预置默认模型列表（API 不可用时降级）
_FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "Qwen/Qwen3-8B", "name": "Qwen3-8B"},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "name": "Qwen2.5-7B-Instruct"},
    {"id": "THUDM/glm-4-9b-chat", "name": "GLM-4-9B-Chat"},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek-V3"},
]


@dataclass
class ModelListResult:
    """模型列表获取结果"""

    models: list[dict[str, str]] = field(default_factory=list)
    is_fallback: bool = False
    error_message: str = ""

    @property
    def is_ok(self) -> bool:
        return not self.is_fallback


class ModelListService:
    """硅基流动模型列表公共服务"""

    def __init__(self, cache_ttl: int = DEFAULT_CACHE_TTL) -> None:
        self._cache_ttl = cache_ttl

    def get_models(self) -> list[dict[str, str]]:
        """获取可用模型列表，优先从缓存读取"""
        result = self.get_result()
        return result.models

    def get_result(self) -> ModelListResult:
        """获取模型列表及连接状态，优先从缓存读取"""
        cached: list[dict[str, str]] | None = cache.get(CACHE_KEY)
        cached_status: dict[str, Any] | None = cache.get(CACHE_KEY_STATUS)
        if cached is not None and cached_status is not None:
            return ModelListResult(
                models=cached,
                is_fallback=cached_status.get("is_fallback", False),
                error_message=cached_status.get("error_message", ""),
            )

        result = self._fetch_from_api()
        cache.set(CACHE_KEY, result.models, self._cache_ttl)
        cache.set(
            CACHE_KEY_STATUS,
            {"is_fallback": result.is_fallback, "error_message": result.error_message},
            self._cache_ttl,
        )
        return result

    def _fetch_from_api(self) -> ModelListResult:
        """调用 SiliconFlow GET /v1/models API"""
        api_key = LLMConfig.get_api_key()
        base_url = LLMConfig.get_base_url()
        if not api_key:
            msg = "SILICONFLOW_API_KEY 未配置，使用默认模型列表"
            logger.warning(msg)
            return ModelListResult(
                models=self._get_fallback_models(),
                is_fallback=True,
                error_message=msg,
            )

        url = f"{base_url.rstrip('/')}/models"
        try:
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                params={"sub_type": "chat"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            models: list[dict[str, str]] = [
                {"id": m["id"], "name": m.get("id", "").split("/")[-1]} for m in data.get("data", []) if m.get("id")
            ]
            if models:
                logger.info("从 SiliconFlow API 获取到 %d 个模型", len(models))
                return ModelListResult(models=models)
        except httpx.HTTPStatusError as exc:
            msg = f"SiliconFlow API 返回 {exc.response.status_code}：{exc.response.text[:200]}"
            logger.error("获取 SiliconFlow 模型列表失败 - %s", msg)
            return ModelListResult(
                models=self._get_fallback_models(),
                is_fallback=True,
                error_message=msg,
            )
        except httpx.ConnectError:
            msg = f"无法连接 SiliconFlow 服务器 ({base_url})"
            logger.error("获取 SiliconFlow 模型列表失败 - %s", msg)
            return ModelListResult(
                models=self._get_fallback_models(),
                is_fallback=True,
                error_message=msg,
            )
        except httpx.TimeoutException:
            msg = f"连接 SiliconFlow 服务器超时 ({base_url})"
            logger.error("获取 SiliconFlow 模型列表失败 - %s", msg)
            return ModelListResult(
                models=self._get_fallback_models(),
                is_fallback=True,
                error_message=msg,
            )
        except Exception:
            msg = "获取 SiliconFlow 模型列表时发生未知错误"
            logger.exception(msg)
            return ModelListResult(
                models=self._get_fallback_models(),
                is_fallback=True,
                error_message=msg,
            )

        # API 返回空列表
        return ModelListResult(
            models=self._get_fallback_models(),
            is_fallback=True,
            error_message="SiliconFlow API 返回空模型列表",
        )

    @staticmethod
    def _get_fallback_models() -> list[dict[str, str]]:
        """返回预置默认模型列表"""
        return list(_FALLBACK_MODELS)
