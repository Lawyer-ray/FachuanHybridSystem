"""LLM 调用审计追踪

将每次 LLM 调用（成功/失败）以 best-effort 方式写入 LLMCallRecord。
追踪写入绝不影响主调用流程：任何异常只记 warning 日志。

开关：SystemConfig 键 LLM_TRACKING_ENABLED（默认开启）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.core.llm.tracking")

_TRACKING_ENABLED_KEY = "LLM_TRACKING_ENABLED"


def is_tracking_enabled() -> bool:
    from .config import LLMConfig

    raw = LLMConfig._get_system_config(_TRACKING_ENABLED_KEY, "true")
    return LLMConfig._parse_bool(raw, True)


async def is_tracking_enabled_async() -> bool:
    from .config import LLMConfig

    raw = await LLMConfig._get_system_config_async(_TRACKING_ENABLED_KEY, "true")
    return LLMConfig._parse_bool(raw, True)


def capture_caller(depth: int = 2) -> str:
    """捕获调用方模块路径（用于审计），仅取栈帧 __name__，失败返回空串。

    depth 语义与 sys._getframe 一致：0 = 本函数，1 = 调用本函数的方法，2 = 更外层。
    """
    import sys

    try:
        frame = sys._getframe(depth)
        return str(frame.f_globals.get("__name__", ""))[:200]
    except (ValueError, AttributeError):
        return ""


def _write_record(**fields: Any) -> None:
    from apps.core.models import LLMCallRecord

    LLMCallRecord.objects.create(**fields)


async def _awrite_record(**fields: Any) -> None:
    from apps.core.models import LLMCallRecord

    await LLMCallRecord.objects.acreate(**fields)


def record_llm_call(
    *,
    backend: str,
    model: str,
    duration_ms: float,
    success: bool = True,
    caller: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    error: BaseException | None = None,
) -> None:
    """同步记录一次 LLM 调用（best-effort，失败仅记日志）。"""
    try:
        if not is_tracking_enabled():
            return
        _write_record(
            model=model or "-",
            backend=backend,
            caller=caller[:200],
            success=success,
            error_type=type(error).__name__ if error else "",
            error_summary=str(error)[:2000] if error else "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.warning("LLM 调用记录写入失败（不影响主流程）", exc_info=True)


async def arecord_llm_call(
    *,
    backend: str,
    model: str,
    duration_ms: float,
    success: bool = True,
    caller: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    error: BaseException | None = None,
) -> None:
    """异步记录一次 LLM 调用（best-effort，失败仅记日志）。"""
    try:
        if not await is_tracking_enabled_async():
            return
        await _awrite_record(
            model=model or "-",
            backend=backend,
            caller=caller[:200],
            success=success,
            error_type=type(error).__name__ if error else "",
            error_summary=str(error)[:2000] if error else "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.warning("LLM 调用记录写入失败（不影响主流程）", exc_info=True)
