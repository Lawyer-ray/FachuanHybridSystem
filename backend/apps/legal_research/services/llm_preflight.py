from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.core.exceptions import ValidationException
from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)


def verify_siliconflow_connectivity(*, model: str | None) -> None:
    """Validate SiliconFlow connectivity and optional model availability before queueing a task."""

    api_key = (LLMConfig.get_api_key() or "").strip()
    if not api_key:
        raise ValidationException("未配置硅基流动 API Key，请先完成系统配置。")

    base_url = (LLMConfig.get_base_url() or "").strip().rstrip("/")
    if not base_url:
        raise ValidationException("未配置硅基流动 Base URL，请先完成系统配置。")

    selected_model = (model or "").strip()
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

    if not selected_model:
        return

    available_models = {
        str(item.get("id") or "").strip()
        for item in (payload.get("data") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if available_models and selected_model not in available_models:
        raise ValidationException(f"所选模型不可用: {selected_model}")
