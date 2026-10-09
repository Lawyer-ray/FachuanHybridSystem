from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.core.exceptions import ValidationException
from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

_BACKEND_LABELS = {
    "openai_compatible": "OpenAI 兼容",
}


def verify_llm_connectivity(*, model: str | None) -> None:  # pragma: no cover
    """Validate LLM connectivity and optional model availability before queueing a task.

    All models route to the OpenAI-compatible backend (AI platform table).
    """
    selected_model = (model or "").strip()
    backend = LLMConfig.resolve_backend_for_model(selected_model)
    logger.info("LLM precheck: model=%s, backend=%s", selected_model, backend)
    configs = LLMConfig.get_backend_configs()
    config = configs.get(backend)

    if not config or not config.enabled:
        raise ValidationException(f"后端 {_BACKEND_LABELS.get(backend, backend)} 未启用，请先完成系统配置。")

    api_key = (config.api_key or "").strip()
    base_url = (config.base_url or "").strip().rstrip("/")

    if not base_url:
        raise ValidationException(f"未配置 {_BACKEND_LABELS.get(backend, backend)} Base URL，请先完成系统配置。")

    if not api_key:
        raise ValidationException(f"未配置 {_BACKEND_LABELS.get(backend, backend)} API Key，请先完成系统配置。")

    _check_openai_compatible(base_url, api_key)


def _check_openai_compatible(base_url: str, api_key: str) -> None:  # pragma: no cover
    try:
        import ssl

        # 安全审计（2026Q4 M-3）：原实现无条件 check_hostname=False +
        # CERT_NONE，而本请求携带 Authorization: Bearer <API Key>——等于每次
        # 连通性预检都把 Key 明文发给任何能拦截连接的对端（律所访客 Wi-Fi、
        # 被劫持的 CDN/代理）。连通性检查本就该验证证书，改回默认上下文。
        ssl_context = ssl.create_default_context()
        transport = httpx.HTTPTransport(verify=ssl_context)
        with httpx.Client(transport=transport, timeout=12.0) as client:
            response = client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.RequestError as exc:
        logger.warning("OpenAI 兼容后端连通性检查失败", extra={"base_url": base_url, "error": str(exc)})
        raise ValidationException(f"OpenAI 兼容后端连接失败: {exc}") from exc

    if response.status_code in (401, 403):
        raise ValidationException("OpenAI 兼容后端鉴权失败，请检查 API Key。")
    if response.status_code != 200:
        raise ValidationException(f"OpenAI 兼容后端服务不可用 (HTTP {response.status_code})。")
