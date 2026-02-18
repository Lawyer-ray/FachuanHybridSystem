"""Module for tracing."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_current_trace_ids() -> tuple[str | None, str | None]:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        context = span.get_span_context()
        if context is None or not context.is_valid:
            return None, None

        return f"{context.trace_id:032x}", f"{context.span_id:016x}"
    except ModuleNotFoundError:
        return None, None
    except Exception:
        logger.exception("操作失败")
        return None, None
