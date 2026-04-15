"""MCP 客户端封装（streamable-http / SSE）。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar, cast

import httpx
from asgiref.sync import async_to_sync
from django.core.cache import cache
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException
from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

logger = logging.getLogger(__name__)

_TRANSPORT_STREAMABLE_HTTP = "streamable_http"
_TRANSPORT_SSE = "sse"
_ResultT = TypeVar("_ResultT")
_TRANSPORT_UNHEALTHY_TTL_SECONDS = 10 * 60


class McpToolClient:
    """对外提供同步调用接口，内部使用 MCP Python SDK 异步客户端。"""

    def __init__(
        self,
        *,
        provider_name: str,
        transport: str,
        base_url: str,
        sse_url: str,
        api_key: str,
        api_keys: tuple[str, ...] | list[str] | None = None,
        timeout_seconds: int = 30,
        rate_limit_requests: int = 60,
        rate_limit_window_seconds: int = 60,
        retry_max_attempts: int = 2,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        self._provider_name = provider_name
        self._transport = (transport or _TRANSPORT_STREAMABLE_HTTP).strip().lower()
        self._base_url = (base_url or "").strip()
        self._sse_url = (sse_url or "").strip()
        normalized_api_keys = [str(item or "").strip() for item in (api_keys or ()) if str(item or "").strip()]
        if not normalized_api_keys and api_key:
            normalized_api_keys = [str(api_key).strip()]
        self._api_key = normalized_api_keys[0] if normalized_api_keys else ""
        self._api_key_pool = McpApiKeyPool(provider_name=provider_name, api_keys=normalized_api_keys)
        self._timeout_seconds = max(5, int(timeout_seconds or 30))
        self._rate_limit_requests = max(1, int(rate_limit_requests or 1))
        self._rate_limit_window_seconds = max(1, int(rate_limit_window_seconds or 1))
        self._retry_max_attempts = max(1, min(5, int(retry_max_attempts or 1)))
        self._retry_backoff_seconds = max(0.0, min(5.0, float(retry_backoff_seconds or 0.0)))

    def call_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用 MCP 工具并返回标准化结果。"""
        self._acquire_rate_limit(action=f"call_tool:{tool_name}")
        started = time.perf_counter()
        result, execution_meta = self._execute_with_api_key_failover(
            action=f"call_tool:{tool_name}",
            operation=lambda api_key, transport: async_to_sync(self._call_tool_async)(
                transport=transport,
                tool_name=tool_name,
                arguments=arguments,
                api_key=api_key,
            ),
            log_context={"tool": tool_name},
        )

        payload = result["payload"]
        raw = result["raw"]
        if raw.get("is_error"):
            raise ValidationException(
                message=f"{self._provider_name} 工具调用返回错误",
                code="MCP_TOOL_ERROR",
                errors={"provider": self._provider_name, "tool": tool_name, "payload": payload},
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        result["transport"] = str(execution_meta.get("transport") or self._transport)
        result["requested_transport"] = self._transport
        result["fallback_used"] = result["transport"] != self._transport
        result["duration_ms"] = max(0, duration_ms)
        result["attempt_count"] = max(1, int(execution_meta.get("attempt_count", 1) or 1))
        result["api_key_pool_size"] = max(1, int(execution_meta.get("api_key_pool_size", 1) or 1))
        result["api_key_attempt_count"] = max(1, int(execution_meta.get("api_key_attempt_count", 1) or 1))
        result["api_key_switched"] = bool(execution_meta.get("api_key_switched", False))
        return cast(dict[str, Any], result)

    def list_tools(self) -> list[str]:
        """获取远端 MCP 可用工具名列表。"""
        return [item["name"] for item in self.describe_tools() if item.get("name")]

    def describe_tools(self) -> list[dict[str, Any]]:
        """获取远端 MCP 工具定义（名称、描述、参数 schema）。"""
        self._acquire_rate_limit(action="describe_tools")
        tools, _meta = self._execute_with_api_key_failover(
            action="describe_tools",
            operation=lambda api_key, transport: async_to_sync(self._describe_tools_async)(
                transport=transport,
                api_key=api_key,
            ),
        )
        return cast(list[dict[str, Any]], tools)

    async def _call_tool_async(
        self,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        async with self._open_session(transport=transport, api_key=api_key) as session:
            result = await session.call_tool(name=tool_name, arguments=arguments)
        payload = self._extract_payload(result)
        return {
            "payload": payload,
            "raw": {
                "is_error": bool(result.isError),
                "structured_content": result.structuredContent,
                "content": [self._serialize_content_item(item) for item in result.content],
            },
        }

    async def _describe_tools_async(self, *, transport: str, api_key: str) -> list[dict[str, Any]]:
        async with self._open_session(transport=transport, api_key=api_key) as session:
            result = await session.list_tools()
        tools: list[dict[str, Any]] = []
        for item in result.tools:
            name = str(getattr(item, "name", "") or "").strip()
            if not name:
                continue
            description = str(getattr(item, "description", "") or "").strip()
            input_schema = getattr(item, "inputSchema", None)
            if input_schema is None:
                input_schema = getattr(item, "input_schema", None)
            if not isinstance(input_schema, dict):
                input_schema = {}
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema,
                }
            )
        return tools

    @asynccontextmanager
    async def _open_session(self, *, transport: str, api_key: str) -> Any:
        headers = self._headers(transport=transport, api_key=api_key)
        if transport == _TRANSPORT_SSE:
            async with sse_client(
                self._sse_url,
                headers=headers,
                timeout=float(self._timeout_seconds),
                sse_read_timeout=max(60.0, float(self._timeout_seconds) * 3),
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        timeout = httpx.Timeout(float(self._timeout_seconds), read=max(60.0, float(self._timeout_seconds) * 3))
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(
                self._base_url,
                http_client=http_client,
                terminate_on_close=True,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

    def _headers(self, *, transport: str, api_key: str) -> dict[str, str]:
        # 天眼查当前网关对不同传输协议的鉴权兼容性并不稳定：
        # - SSE 持续使用标准 Bearer
        # - streamable-http 仍沿用既有 lowercase bearer，并在异常时快速回退到 SSE
        scheme = "bearer" if transport == _TRANSPORT_STREAMABLE_HTTP else "Bearer"
        return {"Authorization": f"{scheme} {str(api_key or self._api_key).strip()}"}

    def _transport_attempts(self) -> list[str]:
        if (
            self._transport == _TRANSPORT_STREAMABLE_HTTP
            and self._sse_url
            and self._is_transport_unhealthy(self._transport)
        ):
            return [_TRANSPORT_SSE]
        attempts = [self._transport]
        if self._transport == _TRANSPORT_STREAMABLE_HTTP and self._sse_url:
            attempts.append(_TRANSPORT_SSE)
        return attempts

    def _execute_with_api_key_failover(
        self,
        *,
        action: str,
        operation: Callable[[str, str], _ResultT],
        log_context: dict[str, Any] | None = None,
    ) -> tuple[_ResultT, dict[str, Any]]:
        api_keys = self._api_key_pool.ordered_keys()
        if not api_keys:
            raise ExternalServiceError(
                message=f"{self._provider_name} API Key 未配置",
                code="MCP_API_KEY_MISSING",
                errors={"provider": self._provider_name, "action": action},
            )

        total_attempt_count = 0
        api_key_attempt_count = 0
        last_error: Exception | None = None
        extra = dict(log_context or {})
        for api_key_index, api_key in enumerate(api_keys):
            api_key_attempt_count += 1
            fingerprint = self._api_key_pool.fingerprint(api_key)
            result, transport_used, transport_attempt_count, current_error = self._run_transport_attempts(
                action=action,
                operation=operation,
                api_key=api_key,
                log_context=extra,
            )
            total_attempt_count += transport_attempt_count
            if current_error is None and result is not None:
                self._api_key_pool.mark_success(api_key)
                return result, {
                    "transport": transport_used,
                    "attempt_count": total_attempt_count,
                    "api_key_pool_size": len(api_keys),
                    "api_key_attempt_count": api_key_attempt_count,
                    "api_key_switched": api_key_attempt_count > 1,
                }
            if current_error is None:
                continue
            last_error = current_error
            if self._should_switch_api_key(current_error):
                self._mark_api_key_failure(api_key=api_key, exc=current_error)
                has_more_keys = api_key_index < len(api_keys) - 1
                if has_more_keys:
                    logger.warning(
                        "MCP request failed with current api key, switch to next key",
                        extra={
                            "provider": self._provider_name,
                            "action": action,
                            "api_key_fingerprint": fingerprint,
                            "api_key_index": api_key_index + 1,
                            "api_key_pool_size": len(api_keys),
                            "error_type": type(current_error).__name__,
                            **extra,
                        },
                    )
                    continue
            self._raise_transport_error(action=action, exc=current_error)

        if last_error is not None:
            self._raise_transport_error(action=action, exc=last_error)
        raise ExternalServiceError(
            message=f"{self._provider_name} 调用异常",
            code="MCP_TRANSPORT_ERROR",
            errors={"provider": self._provider_name, "action": action},
        )

    def _run_transport_attempts(
        self,
        *,
        action: str,
        operation: Callable[[str, str], _ResultT],
        api_key: str,
        log_context: dict[str, Any] | None = None,
    ) -> tuple[_ResultT | None, str, int, Exception | None]:
        attempts = self._transport_attempts()
        last_error: Exception | None = None
        total_attempt_count = 0
        extra = dict(log_context or {})
        for index, transport in enumerate(attempts):
            for retry_index in range(self._retry_max_attempts):
                total_attempt_count += 1
                try:
                    result = operation(api_key, transport)
                    self._clear_transport_unhealthy(transport)
                    return result, transport, total_attempt_count, None
                except Exception as exc:
                    last_error = exc
                    has_more_retry = retry_index < self._retry_max_attempts - 1
                    if has_more_retry and self._should_retry(exc):
                        delay = self._retry_backoff_seconds * (2**retry_index)
                        if delay > 0:
                            time.sleep(delay)
                        logger.warning(
                            "MCP request failed, retry with same transport: %s",
                            exc,
                            extra={
                                "provider": self._provider_name,
                                "action": action,
                                "transport": transport,
                                "retry_index": retry_index + 1,
                                "retry_max_attempts": self._retry_max_attempts,
                                "error_type": type(exc).__name__,
                                **extra,
                            },
                        )
                        continue
                    break

            has_fallback = index < len(attempts) - 1
            if has_fallback and last_error is not None:
                self._mark_transport_unhealthy(transport=transport, exc=last_error)
                logger.warning(
                    "MCP request failed on primary transport, retry with fallback: %s",
                    last_error,
                    extra={
                        "provider": self._provider_name,
                        "action": action,
                        "primary_transport": transport,
                        "fallback_transport": attempts[index + 1],
                        "error_type": type(last_error).__name__,
                        **extra,
                    },
                )
                continue
        return None, self._transport, total_attempt_count, last_error

    def _mark_transport_unhealthy(self, *, transport: str, exc: Exception) -> None:
        if not self._should_quarantine_transport(transport=transport, exc=exc):
            return
        cache.set(self._transport_unhealthy_cache_key(transport), True, timeout=_TRANSPORT_UNHEALTHY_TTL_SECONDS)

    def _clear_transport_unhealthy(self, transport: str) -> None:
        cache.delete(self._transport_unhealthy_cache_key(transport))

    def _is_transport_unhealthy(self, transport: str) -> bool:
        return bool(cache.get(self._transport_unhealthy_cache_key(transport)))

    def _transport_unhealthy_cache_key(self, transport: str) -> str:
        base_digest = hashlib.md5(self._base_url.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"enterprise_data:transport_unhealthy:{self._provider_name}:{transport}:{base_digest}"

    @staticmethod
    def _serialize_content_item(item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return cast(dict[str, Any], item.model_dump(by_alias=True, mode="json", exclude_none=True))
        return {"value": str(item)}

    def _extract_payload(self, result: types.CallToolResult) -> Any:
        if result.structuredContent is not None:
            return result.structuredContent

        parsed_json: list[Any] = []
        plain_text: list[str] = []
        for item in result.content:
            if getattr(item, "type", None) != "text":
                continue
            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue
            parsed = self._try_parse_json(text)
            if parsed is not None:
                parsed_json.append(parsed)
            else:
                plain_text.append(text)

        if len(parsed_json) == 1:
            return parsed_json[0]
        if parsed_json:
            return parsed_json
        if len(plain_text) == 1:
            return plain_text[0]
        if plain_text:
            return plain_text
        return [self._serialize_content_item(item) for item in result.content]

    @staticmethod
    def _try_parse_json(text: str) -> Any | None:
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None

    def _acquire_rate_limit(self, *, action: str) -> None:
        now = int(time.time())
        window = self._rate_limit_window_seconds
        bucket = now // window
        key = f"enterprise_data:rate_limit:{self._provider_name}:{action}:{bucket}"
        expiry = window + 5

        if cache.add(key, 0, timeout=expiry):
            current = cache.incr(key)
        else:
            try:
                current = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=expiry)
                current = 1

        if int(current) <= self._rate_limit_requests:
            return

        retry_after = max(1, (bucket + 1) * window - now)
        raise ValidationException(
            message=f"{self._provider_name} 调用频率过高，请稍后重试",
            code="MCP_RATE_LIMITED",
            errors={
                "provider": self._provider_name,
                "action": action,
                "limit": self._rate_limit_requests,
                "window_seconds": window,
                "retry_after_seconds": retry_after,
            },
        )

    def _should_retry(self, exc: Exception) -> bool:
        for item in self._collect_related_exceptions(exc):
            if isinstance(item, (ValidationException, AuthenticationError)):
                return False
            if isinstance(item, httpx.TimeoutException):
                return True
            if isinstance(item, httpx.ConnectError):
                return True
            if isinstance(item, httpx.HTTPStatusError):
                status_code = int(getattr(item.response, "status_code", 0) or 0)
                if status_code == 429:
                    return False
                return 500 <= status_code < 600
        return False

    def _should_switch_api_key(self, exc: Exception) -> bool:
        for item in self._collect_related_exceptions(exc):
            if isinstance(item, AuthenticationError):
                return True
            if isinstance(item, ExternalServiceError):
                status_code = int((getattr(item, "errors", {}) or {}).get("status_code") or 0)
                if str(getattr(item, "code", "") or "").strip() == "MCP_HTTP_ERROR" and status_code == 429:
                    return True
            if isinstance(item, httpx.HTTPStatusError):
                status_code = int(getattr(item.response, "status_code", 0) or 0)
                if status_code == 429 or self._is_auth_like_http_error(item):
                    return True
        return False

    def _mark_api_key_failure(self, *, api_key: str, exc: Exception) -> None:
        if not api_key:
            return
        for item in self._collect_related_exceptions(exc):
            if isinstance(item, AuthenticationError):
                self._api_key_pool.mark_auth_failed(api_key)
                return
            if isinstance(item, ExternalServiceError):
                status_code = int((getattr(item, "errors", {}) or {}).get("status_code") or 0)
                if str(getattr(item, "code", "") or "").strip() == "MCP_HTTP_ERROR" and status_code == 429:
                    self._api_key_pool.mark_rate_limited(api_key)
                    return
            if isinstance(item, httpx.HTTPStatusError):
                status_code = int(getattr(item.response, "status_code", 0) or 0)
                if self._is_auth_like_http_error(item):
                    self._api_key_pool.mark_auth_failed(api_key)
                    return
                if status_code == 429:
                    self._api_key_pool.mark_rate_limited(api_key)
                    return

    def _should_quarantine_transport(self, *, transport: str, exc: Exception) -> bool:
        if transport != _TRANSPORT_STREAMABLE_HTTP:
            return False
        return True

    def _raise_transport_error(self, *, action: str, exc: Exception) -> None:
        collected = self._collect_related_exceptions(exc)
        for item in collected:
            if isinstance(item, (ValidationException, AuthenticationError, ExternalServiceError)):
                raise item

        for item in collected:
            if not isinstance(item, httpx.HTTPStatusError):
                continue
            status_code = int(getattr(item.response, "status_code", 0) or 0)
            if self._is_auth_like_http_error(item):
                raise AuthenticationError(
                    message=f"{self._provider_name} 鉴权失败，请检查 API Key",
                    code="MCP_AUTH_ERROR",
                    errors={"provider": self._provider_name, "status_code": status_code},
                ) from exc
            raise ExternalServiceError(
                message=f"{self._provider_name} 调用失败（HTTP {status_code}）",
                code="MCP_HTTP_ERROR",
                errors={"provider": self._provider_name, "action": action, "status_code": status_code},
            ) from exc

        for item in collected:
            if not isinstance(item, httpx.TimeoutException):
                continue
            raise ExternalServiceError(
                message=f"{self._provider_name} 调用超时",
                code="MCP_TIMEOUT",
                errors={"provider": self._provider_name, "action": action, "timeout_seconds": self._timeout_seconds},
            ) from exc

        for item in collected:
            if not isinstance(item, httpx.ConnectError):
                continue
            raise ExternalServiceError(
                message=f"{self._provider_name} 网络连接失败",
                code="MCP_NETWORK_ERROR",
                errors={"provider": self._provider_name, "action": action},
            ) from exc

        logger.exception(
            "MCP transport failed",
            extra={"provider": self._provider_name, "action": action, "error_type": type(exc).__name__},
        )
        raise ExternalServiceError(
            message=f"{self._provider_name} 调用异常",
            code="MCP_TRANSPORT_ERROR",
            errors={"provider": self._provider_name, "action": action, "error_type": type(exc).__name__},
        ) from exc

    @staticmethod
    def _is_auth_like_http_error(error: httpx.HTTPStatusError) -> bool:
        status_code = int(getattr(error.response, "status_code", 0) or 0)
        if status_code in (401, 403):
            return True

        response = getattr(error, "response", None)
        if response is None:
            return False

        lowered_text = ""
        try:
            lowered_text = str(response.text or "").lower()
        except Exception:
            lowered_text = ""
        if McpToolClient._contains_auth_token(lowered_text):
            return True

        try:
            body = response.json()
        except Exception:
            return False

        flattened_hint = McpToolClient._flatten_error_payload_text(body)
        if not flattened_hint:
            return False
        return McpToolClient._contains_auth_token(flattened_hint)

    @staticmethod
    def _contains_auth_token(text: str) -> bool:
        normalized = str(text or "").lower()
        auth_tokens = (
            "auth_error",
            "authentication",
            "authentication_error",
            "unauthorized",
            "invalid api key",
            "apikey",
            "api key",
            "token",
            "signature",
        )
        return any(token in normalized for token in auth_tokens)

    @staticmethod
    def _flatten_error_payload_text(payload: Any) -> str:
        fragments: list[str] = []

        def _walk(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, (str, int, float, bool)):
                text = str(value).strip().lower()
                if text:
                    fragments.append(text)
                return
            if isinstance(value, dict):
                for key, nested in value.items():
                    key_text = str(key).strip().lower()
                    if key_text:
                        fragments.append(key_text)
                    _walk(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    _walk(nested)
                return

        _walk(payload)
        return " ".join(fragments)

    @staticmethod
    def _collect_related_exceptions(exc: BaseException) -> list[BaseException]:
        queue: list[BaseException] = [exc]
        seen: set[int] = set()
        collected: list[BaseException] = []

        while queue:
            current = queue.pop(0)
            marker = id(current)
            if marker in seen:
                continue
            seen.add(marker)
            collected.append(current)

            if isinstance(current, BaseExceptionGroup):
                queue.extend(current.exceptions)

            cause = getattr(current, "__cause__", None)
            if isinstance(cause, BaseException):
                queue.append(cause)

            context = getattr(current, "__context__", None)
            if isinstance(context, BaseException):
                queue.append(context)

        return collected
