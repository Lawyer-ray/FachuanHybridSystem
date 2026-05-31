from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.core.exceptions import ValidationException
from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

_BACKEND_LABELS = {
    "siliconflow": "硅基流动",
    "ollama": "Ollama",
    "openai_compatible": "OpenAI 兼容",
}

def verify_siliconflow_connectivity(*, model: str | None) -> None:
    """Validate LLM connectivity and optional model availability before queueing a task.

    Routes to the correct backend based on the model name:
    - "/" in model → SiliconFlow
    - ":" in model → Ollama
    - otherwise → OpenAI-compatible
    """
    selected_model = (model or "").strip()
    backend = LLMConfig.resolve_backend_for_model(selected_model)
    logger.info("LLM precheck: model=%s, backend=%s", selected_model, backend)
    configs = LLMConfig.get_backend_configs()
    config = configs.get(backend)

    if not config or not config.enabled:
        raise ValidationException(
            f"后端 {_BACKEND_LABELS.get(backend, backend)} 未启用，请先完成系统配置。"
        )

    api_key = (config.api_key or "").strip()
    base_url = (config.base_url or "").strip().rstrip("/")

    if not base_url:
        raise ValidationException(
            f"未配置 {_BACKEND_LABELS.get(backend, backend)} Base URL，请先完成系统配置。"
        )

    # Ollama 不需要 API Key，检查 /api/tags
    if backend == "ollama":
        _check_ollama(base_url, selected_model)
        return

    # SiliconFlow 和 OpenAI-compatible 需要 API Key
    if not api_key:
        raise ValidationException(
            f"未配置 {_BACKEND_LABELS.get(backend, backend)} API Key，请先完成系统配置。"
        )

    # OpenAI-compatible: 只检查连通性，不验证模型列表（各提供商模型列表差异大）
    if backend == "openai_compatible":
        _check_openai_compatible(base_url, api_key)
        return

    # SiliconFlow: 检查连通性 + 模型可用性
    _check_siliconflow(base_url, api_key, selected_model)

def _check_siliconflow(base_url: str, api_key: str, model: str) -> None:
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"sub_type": "chat"},
            timeout=12.0,
        )
    except httpx.RequestError as exc:
        logger.warning("硅基流动连通性检查失败", extra={"base_url": base_url, "error": str(exc)})
        raise ValidationException(f"硅基流动连接失败: {exc}") from exc

    if response.status_code in (401, 403):
        raise ValidationException("硅基流动鉴权失败，请检查 API Key。")
    if response.status_code != 200:
        raise ValidationException(f"硅基流动服务不可用 (HTTP {response.status_code})。")

    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise ValidationException("硅基流动返回了不可解析的响应。") from exc

    if not model:
        return

    available_models = {
        str(item.get("id") or "").strip()
        for item in (payload.get("data") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if available_models and model not in available_models:
        raise ValidationException(f"所选模型不可用: {model}")

def _check_openai_compatible(base_url: str, api_key: str) -> None:
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=12.0,
        )
    except httpx.RequestError as exc:
        logger.warning("OpenAI 兼容后端连通性检查失败", extra={"base_url": base_url, "error": str(exc)})
        raise ValidationException(f"OpenAI 兼容后端连接失败: {exc}") from exc

    if response.status_code in (401, 403):
        raise ValidationException("OpenAI 兼容后端鉴权失败，请检查 API Key。")
    if response.status_code != 200:
        raise ValidationException(f"OpenAI 兼容后端服务不可用 (HTTP {response.status_code})。")

def _check_ollama(base_url: str, model: str) -> None:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=12.0)
    except httpx.RequestError as exc:
        logger.warning("Ollama 连通性检查失败", extra={"base_url": base_url, "error": str(exc)})
        raise ValidationException(f"Ollama 连接失败: {exc}") from exc

    if response.status_code != 200:
        raise ValidationException(f"Ollama 服务不可用 (HTTP {response.status_code})。")
