"""Module for httpx clients."""

import logging
import os
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger("apps.core.httpx_clients")


def _httpx_event_hooks() -> dict[str, list[Callable[..., Any]]] | None:
    enabled = os.environ.get("DJANGO_HTTPX_METRICS", "").lower() in ("true", "1", "yes")
    if not enabled:
        return None

    def _on_request(request: httpx.Request) -> None:
        try:
            request.extensions["metrics_started_at"] = time.perf_counter()
        except Exception:
            logger.exception("操作失败")

            return

    def _on_response(response: httpx.Response) -> None:
        try:
            started_at = response.request.extensions.get("metrics_started_at")
            if started_at is None:
                return
            duration_ms = int((time.perf_counter() - float(started_at)) * 1000.0)
            host = str(getattr(response.request.url, "host", "") or "")
            from apps.core.telemetry.metrics import record_httpx

            record_httpx(
                host=host,
                method=str(response.request.method or "UNKNOWN"),
                status_code=int(getattr(response, "status_code", 0) or 0),
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception("操作失败")

            return

    return {"request": [_on_request], "response": [_on_response]}


@lru_cache(maxsize=1)
def get_sync_http_client() -> httpx.Client:
    event_hooks = _httpx_event_hooks()
    return httpx.Client(
        timeout=httpx.Timeout(60.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        follow_redirects=True,
        event_hooks=event_hooks,
    )


@lru_cache(maxsize=1)
def get_async_http_client() -> httpx.AsyncClient:
    event_hooks = _httpx_event_hooks()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        follow_redirects=True,
        event_hooks=event_hooks,
    )


async def aclose_http_clients() -> None:
    try:
        await get_async_http_client().aclose()
    except Exception as e:
        logger.debug(
            "关闭 async http client 失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True
        )
    try:
        get_sync_http_client().close()
    except Exception as e:
        logger.debug(
            "关闭 sync http client 失败", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True
        )
