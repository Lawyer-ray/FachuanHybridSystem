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


def warm_llm_system_config_cache(keys: Iterable[str] | None = None, *, strict: bool = False) -> dict[str, object]:
    llm_keys = (
        list(keys)
        if keys is not None
        else [
            "SILICONFLOW_API_KEY",
            "SILICONFLOW_BASE_URL",
            "SILICONFLOW_DEFAULT_MODEL",
            "SILICONFLOW_TIMEOUT",
            "SILICONFLOW_ENABLE_TRACKING",
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
