"""Module for warmup."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

logger = logging.getLogger("apps.core.llm")

_LLM_WARMUP_STATE: dict[str, object] = {
    "ok": False,
    "timestamp": None,
    "loaded_keys": [],
    "error": None,
}


def _is_external_outage(exc: BaseException) -> bool:
    """外部依赖（Redis/数据库）临时不可用，属可自愈场景，无需打 ERROR 堆栈。"""
    from django.db.utils import OperationalError

    if isinstance(exc, OperationalError):
        return True
    try:
        from redis.exceptions import ConnectionError as RedisConnectionError
    except Exception:
        return False
    return isinstance(exc, RedisConnectionError)


def warm_llm_system_config_cache(keys: Iterable[str] | None = None, *, strict: bool = False) -> dict[str, object]:
    llm_keys = (
        list(keys)
        if keys is not None
        else [
            "OPENAI_COMPATIBLE_API_KEY",
            "OPENAI_COMPATIBLE_BASE_URL",
            "OPENAI_COMPATIBLE_DEFAULT_MODEL",
            "OPENAI_COMPATIBLE_TIMEOUT",
            "OLLAMA_MODEL",
            "OLLAMA_BASE_URL",
            "LLM_DEFAULT_BACKEND",
        ]
    )

    try:
        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService()
        values = service.warm_cache(llm_keys, timeout=None)
        logger.info(
            "llm_config_warmup_succeeded",
            extra={"loaded_keys": sorted(values.keys()), "requested_count": len(llm_keys)},
        )
        _LLM_WARMUP_STATE.update(
            {
                "ok": True,
                "timestamp": time.time(),
                "loaded_keys": sorted(values.keys()),
                "error": None,
            }
        )
        return dict(_LLM_WARMUP_STATE)
    except Exception as e:
        if _is_external_outage(e):
            logger.warning(
                "llm_config_warmup_skipped: %s 不可用，跳过预热（后续请求按需自愈）",
                type(e).__name__,
            )
        else:
            logger.exception("llm_config_warmup_failed", extra={"error_type": type(e).__name__})
        _LLM_WARMUP_STATE.update(
            {
                "ok": False,
                "timestamp": time.time(),
                "loaded_keys": [],
                "error": str(e),
            }
        )
        if strict:
            raise
        return dict(_LLM_WARMUP_STATE)


def get_llm_warmup_state() -> dict[str, object]:
    return dict(_LLM_WARMUP_STATE)
