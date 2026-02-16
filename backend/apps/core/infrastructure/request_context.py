"""Module for request context."""

from __future__ import annotations

import contextvars
import uuid

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)


def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]


def set_request_context(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> None:
    if request_id is not None:
        request_id_var.set(request_id)
    if trace_id is not None:
        trace_id_var.set(trace_id)
    if span_id is not None:
        span_id_var.set(span_id)


def clear_request_context() -> None:
    request_id_var.set(None)
    trace_id_var.set(None)
    span_id_var.set(None)


def get_request_id(*, fallback_generate: bool = True) -> str | None:
    value = request_id_var.get()
    if value:
        return value
    if not fallback_generate:
        return None
    value = generate_request_id()
    request_id_var.set(value)
    return value


def get_trace_ids() -> tuple[str | None, str | None]:
    return trace_id_var.get(), span_id_var.get()
