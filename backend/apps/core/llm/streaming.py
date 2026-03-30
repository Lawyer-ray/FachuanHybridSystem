"""Module for streaming."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from .backends import ILLMBackend, LLMStreamChunk
from .exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMNetworkError,
    LLMTimeoutError,
)

logger = logging.getLogger("apps.core.llm.streaming")
_RETRIABLE_ERRORS = (LLMTimeoutError, LLMNetworkError, LLMAPIError)


def _resolve_backends(
    get_backend: Callable[[str], ILLMBackend],
    get_backends_by_priority: Callable[[], list[tuple[str, ILLMBackend]]],
    backend: str | None,
    fallback: bool,
) -> list[tuple[str, ILLMBackend]]:
    """解析要尝试的后端列表"""
    if backend:
        backends_to_try: list[tuple[str, ILLMBackend]] = [(backend, get_backend(backend))]
        if fallback:
            for name, b in get_backends_by_priority():
                if name != backend:
                    backends_to_try.append((name, b))
        return backends_to_try
    return get_backends_by_priority()


def _handle_stream_error(
    name: str, e: Exception, fallback: bool, errors: list[Any], log_prefix: str = "stream"
) -> None:
    """处理流式调用错误"""
    errors.append((name, e))
    if isinstance(e, _RETRIABLE_ERRORS):
        logger.warning(
            f"后端 {log_prefix} 调用失败,尝试下一个",
            extra={"backend": name, "error": str(e), "error_type": type(e).__name__},
        )
        if not fallback:
            raise
    else:
        logger.warning(
            f"后端 {log_prefix} 调用发生未知错误",
            extra={"backend": name, "error": str(e), "error_type": type(e).__name__},
        )
        if not fallback:
            raise LLMAPIError(message=f"调用后端 {name} 时发生错误: {e!s}", errors={"detail": str(e)}) from e


def _build_stream_kwargs(
    messages: Any,
    model: Any,
    temperature: Any,
    max_tokens: Any,
    extra_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs = {"messages": messages, "model": model, "temperature": temperature, "max_tokens": max_tokens}
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    return kwargs


def stream_with_fallback(
    *,
    get_backend: Callable[[str], ILLMBackend],
    get_backends_by_priority: Callable[[], list[tuple[str, ILLMBackend]]],
    backend: str | None,
    fallback: bool,
    messages: list[dict[str, str]],
    model: str | None,
    temperature: float,
    max_tokens: int | None,
    **kwargs: Any,
) -> Iterator[LLMStreamChunk]:
    from .fallback_policy import _diagnose_unavailable

    kwargs = _build_stream_kwargs(messages, model, temperature, max_tokens, kwargs)
    if backend and (not fallback):
        yield from get_backend(backend).stream(**kwargs)
        return
    backends_to_try = _resolve_backends(get_backend, get_backends_by_priority, backend, fallback)
    errors: list[tuple[str, Exception]] = []
    skipped: list[tuple[str, str]] = []
    for name, backend_instance in backends_to_try:
        if not backend_instance.is_available():
            reason = _diagnose_unavailable(name, backend_instance)
            logger.warning("后端不可用,跳过", extra={"backend": name, "reason": reason})
            skipped.append((name, reason))
            continue
        it = None
        try:
            it = iter(backend_instance.stream(**kwargs))
            first = next(it)
        except StopIteration:
            return
        except LLMAuthenticationError:
            raise
        except Exception as e:
            logger.exception("操作失败")
            _handle_stream_error(name, e, fallback, errors, "stream")
            continue
        yield first
        if it is not None:
            yield from it
        return
    attempts_detail = [(n, str(e)) for n, e in errors]
    attempts_detail.extend([(n, reason) for n, reason in skipped])
    raise LLMBackendUnavailableError(
        message="所有 LLM 后端均不可用",
        errors={"attempts": attempts_detail, "skipped": skipped},
    )


async def astream_with_fallback(
    *,
    get_backend: Callable[[str], ILLMBackend],
    get_backends_by_priority: Callable[[], list[tuple[str, ILLMBackend]]],
    backend: str | None,
    fallback: bool,
    messages: list[dict[str, str]],
    model: str | None,
    temperature: float,
    max_tokens: int | None,
    **kwargs: Any,
) -> AsyncIterator[LLMStreamChunk]:
    from .fallback_policy import _diagnose_unavailable

    kwargs = _build_stream_kwargs(messages, model, temperature, max_tokens, kwargs)
    if backend and (not fallback):
        async for chunk in get_backend(backend).astream(**kwargs):  # type: ignore[attr-defined]
            yield chunk
        return
    backends_to_try = _resolve_backends(get_backend, get_backends_by_priority, backend, fallback)
    errors: list[tuple[str, Exception]] = []
    skipped: list[tuple[str, str]] = []
    for name, backend_instance in backends_to_try:
        if not backend_instance.is_available():
            reason = _diagnose_unavailable(name, backend_instance)
            logger.warning("后端不可用,跳过", extra={"backend": name, "reason": reason})
            skipped.append((name, reason))
            continue
        try:
            ait = backend_instance.astream(**kwargs).__aiter__()  # type: ignore[attr-defined]
            first = await ait.__anext__()
        except StopAsyncIteration:
            return
        except LLMAuthenticationError:
            raise
        except Exception as e:
            logger.exception("操作失败")
            _handle_stream_error(name, e, fallback, errors, "astream")
            continue
        yield first
        async for chunk in ait:
            yield chunk
        return
    attempts_detail = [(n, str(e)) for n, e in errors]
    attempts_detail.extend([(n, reason) for n, reason in skipped])
    raise LLMBackendUnavailableError(
        message="所有 LLM 后端均不可用",
        errors={"attempts": attempts_detail, "skipped": skipped},
    )
