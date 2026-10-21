"""从 LLMProvider 生成 pi 的 models.json。

## 为什么要生成

pi 的模型来自 ``models.json``（文件），而本系统的 LLM 配置在数据库
（``core.LLMProvider``：base_url + 多 Key 池 + 模型白名单）。两边不打通，
用户在 Admin 改配置后 agent 不生效，是运维陷阱。

这里在建立 pi 会话前，把当前 LLMProvider 渲染成 ``models.json`` 写进该会话
的独立配置目录，使 **Admin 里的配置就是 agent 用的配置**。

## 与多 Key 池的关系

pi 只接受一个 ``apiKey``。系统的多 Key 轮询（``core.llm.key_pool``）在
**服务路径**上生效；agent 路径这里取「第一个可用 Key」，并在多个会话间
轮转（``_round_robin``），使并发时 Key 的使用分散开。

真正做到「每个请求都走 Key 池」需要一层网关（把 ``baseUrl`` 指向自家
网关，由网关做 Key 轮换）。本模块预留了 ``FACHUAN_PI_GATEWAY_URL``：
设置后 ``baseUrl`` 直接指向网关，Key 由网关管理，pi 侧不再持有真实 Key。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GATEWAY_URL_ENV = "FACHUAN_PI_GATEWAY_URL"
GATEWAY_KEY_ENV = "FACHUAN_PI_GATEWAY_KEY"
DEFAULT_CONTEXT_WINDOW = 128000
DEFAULT_MAX_TOKENS = 8192

_rotation_lock = threading.Lock()
_rotation_cursor = 0


def _next_key(keys: list[str]) -> str:
    """会话间轮转 Key，避免所有会话压在同一把 Key 上。"""
    global _rotation_cursor
    if not keys:
        return ""
    with _rotation_lock:
        key = keys[_rotation_cursor % len(keys)]
        _rotation_cursor += 1
    return key


def _load_provider(model_hint: str = "") -> Any:
    """读取启用的 LLMProvider；失败时返回 None（调用方降级）。"""
    try:
        from apps.core.models.llm_provider import LLMProvider
    except Exception:
        logger.debug("无法导入 LLMProvider", exc_info=True)
        return None

    try:
        queryset = LLMProvider.objects.filter(enabled=True).order_by("priority", "name")
        for provider in queryset:
            models = _provider_models(provider)
            if not model_hint or model_hint in models or not models:
                return provider
        return queryset.first()
    except Exception:
        logger.debug("查询 LLMProvider 失败", exc_info=True)
        return None


def _provider_keys_and_models(provider: Any) -> tuple[list[str], dict[str, list[str]]]:
    """解析 provider 的 Key 及其模型白名单。

    ``api_keys`` 是原始文本，格式为 ``key`` 或 ``key|model1,model2``（每行一条），
    必须走 ``LLMProvider.parse_key_entries``，不能当字符串逐字符处理。
    """
    raw = getattr(provider, "api_keys", "") or ""
    try:
        from apps.core.models.llm_provider import parse_key_entries

        entries = parse_key_entries(str(raw))
    except Exception:
        logger.debug("解析 api_keys 失败", exc_info=True)
        entries = [(line.strip(), []) for line in str(raw).splitlines() if line.strip()]

    keys: list[str] = []
    scopes: dict[str, list[str]] = {}
    for key, models in entries:
        if not key or key in keys:
            continue
        keys.append(key)
        if models:
            scopes[key] = list(models)
    return keys, scopes


def _provider_models(provider: Any) -> list[str]:
    """provider 支持的模型列表（默认模型 + extra_models + Key 白名单）。"""
    models: list[str] = []
    default = str(getattr(provider, "default_model", "") or "").strip()
    if default:
        models.append(default)
    extra = str(getattr(provider, "extra_models", "") or "")
    for part in extra.replace(";", ",").split(","):
        name = part.strip()
        if name and name not in models:
            models.append(name)
    return models


def build_models_json(model_hint: str = "") -> dict[str, Any] | None:
    """把当前 LLMProvider 渲染成 pi 的 models.json 内容。

    Returns:
        ``models.json`` 的 dict；无可用 provider 时返回 ``None``
        （此时 pi 用自己的用户级配置，不做任何覆盖）。
    """
    gateway = os.environ.get(GATEWAY_URL_ENV, "").strip()
    provider = _load_provider(model_hint)

    if gateway:
        # 网关模式：baseUrl 指向自家网关，pi 不持有真实 Key
        models = _provider_models(provider) if provider is not None else []
        if model_hint and model_hint not in models:
            models.insert(0, model_hint)
        if not models:
            models = [model_hint] if model_hint else []
        if not models:
            return None
        return {
            "providers": {
                "fachuan": {
                    "baseUrl": gateway,
                    "api": "openai-completions",
                    "apiKey": os.environ.get(GATEWAY_KEY_ENV, "gateway"),
                    "models": [
                        {
                            "id": name,
                            "contextWindow": DEFAULT_CONTEXT_WINDOW,
                            "maxTokens": DEFAULT_MAX_TOKENS,
                        }
                        for name in models
                    ],
                }
            }
        }

    if provider is None:
        return None

    base_url = str(getattr(provider, "base_url", "") or "").strip()
    keys, _scopes = _provider_keys_and_models(provider)
    if not base_url or not keys:
        logger.warning("LLMProvider 缺少 base_url 或 api_key，pi 将使用自身配置")
        return None

    models = _provider_models(provider)
    if model_hint and model_hint not in models:
        models.insert(0, model_hint)
    if not models:
        return None

    return {
        "providers": {
            "fachuan": {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": _next_key(keys),
                "models": [
                    {
                        "id": name,
                        "contextWindow": DEFAULT_CONTEXT_WINDOW,
                        "maxTokens": DEFAULT_MAX_TOKENS,
                    }
                    for name in models
                ],
            }
        }
    }


def write_models_json(target_dir: str | Path, model_hint: str = "") -> Path | None:
    """把 models.json 写进目标目录；无可用配置时返回 ``None``。"""
    payload = build_models_json(model_hint)
    if payload is None:
        return None
    path = Path(target_dir) / "models.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with_suppress = __import__("contextlib").suppress(OSError)
    with with_suppress:
        path.chmod(0o600)
    return path
