"""MCP 传输层封装（streamable-http / SSE）。"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from asgiref.sync import async_to_sync
from django.core.cache import cache
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException

logger = logging.getLogger(__name__)

_TRANSPORT_STREAMABLE_HTTP = "streamable_http"
_TRANSPORT_SSE = "sse"


class McpToolTransport:
    """对外提供同步调用接口，内部使用 MCP Python SDK 异步客户端。"""

    def __init__(
        self,
        *,
        provider_name: str,
        transport: str,
        base_url: str,
        sse_url: str,
        api_key: str,
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
        self._api_key = (api_key or "").strip()
        self._timeout_seconds = max(5, int(timeout_seconds or 30))
        self._rate_limit_requests = max(1, int(rate_limit_requests or 1))
        self._rate_limit_window_seconds = max(1, int(rate_limit_window_seconds or 1))
        self._retry_max_attempts = max(1, min(5, int(retry_max_attempts or 1)))
        self._retry_backoff_seconds = max(0.0, min(5.0, float(retry_backoff_seconds or 0.0)))

    def call_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用 MCP 工具并返回标准化结果。"""
        self._acquire_rate_limit(action=f"call_tool:{tool_name}")
        attempts = self._transport_attempts()
        result: dict[str, Any] | None = None
        used_transport = self._transport
        total_attempt_count = 0
        started = time.perf_counter()
        for index, transport in enumerate(attempts):
            last_error: Exception | None = None
            for retry_index in range(self._retry_max_attempts):
                total_attempt_count += 1
                try:
                    result = async_to_sync(self._call_tool_async)(
                        transport=transport,
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                    used_transport = transport
                    break
                except Exception as exc:
                    last_error = exc
                    has_more_retry = retry_index < self._retry_max_attempts - 1
                    if has_more_retry and self._should_retry(exc):
                        delay = self._retry_backoff_seconds * (2**retry_index)
                        if delay > 0:
                            time.sleep(delay)
                        logger.warning(
                            "MCP call failed, retry with same transport",
                            extra={
                                "provider": self._provider_name,
                                "tool": tool_name,
                                "transport": transport,
                                "retry_index": retry_index + 1,
                                "retry_max_attempts": self._retry_max_attempts,
                                "error_type": type(exc).__name__,
                            },
                        )
                        continue
                    break

            if result is not None:
                break

            has_fallback = index < len(attempts) - 1
            if has_fallback and last_error is not None:
                logger.warning(
                    "MCP call failed on primary transport, retry with fallback",
                    extra={
                        "provider": self._provider_name,
                        "tool": tool_name,
                        "primary_transport": transport,
                        "fallback_transport": attempts[index + 1],
                        "error_type": type(last_error).__name__,
                    },
                )
                continue
            if last_error is not None:
                self._raise_transport_error(action=f"call_tool:{tool_name}", exc=last_error)

        if result is None:
            raise ExternalServiceError(
                message=f"{self._provider_name} 调用异常",
                code="MCP_TRANSPORT_ERROR",
                errors={"provider": self._provider_name, "action": f"call_tool:{tool_name}"},
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
        result["transport"] = used_transport
        result["requested_transport"] = self._transport
        result["fallback_used"] = used_transport != self._transport
        result["duration_ms"] = max(0, duration_ms)
        result["attempt_count"] = max(1, total_attempt_count)
        return result

    def list_tools(self) -> list[str]:
        """获取远端 MCP 可用工具名列表。"""
        return [item["name"] for item in self.describe_tools() if item.get("name")]

    def describe_tools(self) -> list[dict[str, Any]]:
        """获取远端 MCP 工具定义（名称、描述、参数 schema）。"""
        self._acquire_rate_limit(action="describe_tools")
        attempts = self._transport_attempts()
        for index, transport in enumerate(attempts):
            last_error: Exception | None = None
            for retry_index in range(self._retry_max_attempts):
                try:
                    return async_to_sync(self._describe_tools_async)(transport=transport)
                except Exception as exc:
                    last_error = exc
                    has_more_retry = retry_index < self._retry_max_attempts - 1
                    if has_more_retry and self._should_retry(exc):
                        delay = self._retry_backoff_seconds * (2**retry_index)
                        if delay > 0:
                            time.sleep(delay)
                        logger.warning(
                            "MCP describe_tools failed, retry with same transport",
                            extra={
                                "provider": self._provider_name,
                                "transport": transport,
                                "retry_index": retry_index + 1,
                                "retry_max_attempts": self._retry_max_attempts,
                                "error_type": type(exc).__name__,
                            },
                        )
                        continue
                    break

            has_fallback = index < len(attempts) - 1
            if has_fallback and last_error is not None:
                logger.warning(
                    "MCP describe_tools failed on primary transport, retry with fallback",
                    extra={
                        "provider": self._provider_name,
                        "primary_transport": transport,
                        "fallback_transport": attempts[index + 1],
                        "error_type": type(last_error).__name__,
                    },
                )
                continue
            if last_error is not None:
                self._raise_transport_error(action="describe_tools", exc=last_error)
        return []

    async def _call_tool_async(
        self,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._open_session(transport=transport) as session:
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

    async def _describe_tools_async(self, *, transport: str) -> list[dict[str, Any]]:
        async with self._open_session(transport=transport) as session:
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
    async def _open_session(self, *, transport: str) -> Any:
        headers = self._headers(transport=transport)
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

    def _headers(self, *, transport: str) -> dict[str, str]:
        # 兼容天眼查当前网关行为：
        # - streamable-http 对小写 bearer 更稳定
        # - SSE 对标准 Bearer 更稳定
        scheme = "bearer" if transport == _TRANSPORT_STREAMABLE_HTTP else "Bearer"
        return {"Authorization": f"{scheme} {self._api_key}"}

    def _transport_attempts(self) -> list[str]:
        attempts = [self._transport]
        if self._transport == _TRANSPORT_STREAMABLE_HTTP and self._sse_url:
            attempts.append(_TRANSPORT_SSE)
        return attempts

    @staticmethod
    def _serialize_content_item(item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(by_alias=True, mode="json", exclude_none=True)
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
                    return True
                return 500 <= status_code < 600
        return False

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
        if any(token in lowered_text for token in ("auth_error", "authentication", "unauthorized", "invalid api key")):
            return True

        try:
            body = response.json()
        except Exception:
            return False
        if not isinstance(body, dict):
            return False

        hint = " ".join(str(body.get(key, "")) for key in ("type", "code", "detail", "message")).lower()
        return any(token in hint for token in ("auth", "unauthor", "api key", "token"))

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
