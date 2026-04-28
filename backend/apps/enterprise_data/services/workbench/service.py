"""MCP 调试工作台服务实现。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from django.core.cache import cache
from django.db.models import QuerySet
from django.utils import timezone

from apps.core.exceptions import PermissionDenied, ValidationException
from apps.core.security.scrub import scrub_for_storage
from apps.enterprise_data.models import McpWorkbenchExecution
from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService
from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry
from apps.enterprise_data.services.types import (
    DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
    DEFAULT_ALERT_MIN_SAMPLES,
    DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
    DEFAULT_METRICS_WINDOW_SECONDS,
)

_SAMPLE_CACHE_TTL_SECONDS = 24 * 60 * 60
_MAX_SAMPLE_JSON_CHARS = 12000


class McpWorkbenchService:
    """供 Admin 调试页面使用的 MCP 工具编排服务。"""

    def __init__(
        self,
        *,
        registry: EnterpriseProviderRegistry | None = None,
        sample_ttl_seconds: int = _SAMPLE_CACHE_TTL_SECONDS,
        persist_history: bool = True,
        enforce_superuser: bool = True,
        metrics_service: EnterpriseDataMetricsService | None = None,
    ) -> None:
        self._registry = registry or EnterpriseProviderRegistry()
        self._sample_ttl_seconds = max(60, int(sample_ttl_seconds))
        self._persist_history = bool(persist_history)
        self._enforce_superuser = bool(enforce_superuser)
        self._metrics = metrics_service or EnterpriseDataMetricsService(
            window_seconds=self._read_registry_int("get_metrics_window_seconds", DEFAULT_METRICS_WINDOW_SECONDS),
            alert_min_samples=self._read_registry_int("get_alert_min_samples", DEFAULT_ALERT_MIN_SAMPLES),
            alert_success_rate_threshold=self._read_registry_float(
                "get_alert_success_rate_threshold",
                DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
            ),
            alert_fallback_rate_threshold=self._read_registry_float(
                "get_alert_fallback_rate_threshold",
                DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
            ),
            alert_avg_latency_ms_threshold=self._read_registry_int(
                "get_alert_avg_latency_ms_threshold",
                DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
            ),
        )

    def list_providers(self) -> list[dict[str, Any]]:
        descriptors = self._registry.list_providers()
        return [
            {
                "name": item.name,
                "enabled": item.enabled,
                "is_default": item.is_default,
                "transport": item.transport,
                "capabilities": item.capabilities,
            }
            for item in descriptors
        ]

    def describe_tools(self, *, provider: str | None = None, actor_is_superuser: bool = False) -> dict[str, Any]:
        self._ensure_superuser(actor_is_superuser=actor_is_superuser)
        selected_provider = self._registry.get_provider(provider)
        provider_name = selected_provider.name
        tools = selected_provider.describe_tools()
        normalized_tools: list[dict[str, Any]] = []
        for tool in tools:
            tool_name = str(tool.get("name", "") or "").strip()
            if not tool_name:
                continue
            input_schema = tool.get("input_schema")
            if not isinstance(input_schema, dict):
                input_schema = {}
            required = input_schema.get("required")
            if not isinstance(required, list):
                required = []
            sample = self._load_sample(provider=provider_name, tool_name=tool_name)
            normalized_tools.append(
                {
                    "name": tool_name,
                    "description": str(tool.get("description", "") or "").strip(),
                    "input_schema": input_schema,
                    "required_fields": [str(item) for item in required if isinstance(item, str)],
                    "sample": sample if isinstance(sample, dict) else None,
                }
            )
        normalized_tools.sort(key=lambda item: item["name"])
        return {
            "provider": provider_name,
            "transport": selected_provider.transport,
            "tools": normalized_tools,
        }

    def execute_tool(
        self,
        *,
        provider: str | None = None,
        tool_name: str,
        arguments: dict[str, Any],
        actor_username: str = "",
        actor_is_superuser: bool = False,
        replay_of_id: int | None = None,
    ) -> dict[str, Any]:
        self._ensure_superuser(actor_is_superuser=actor_is_superuser)
        normalized_tool = str(tool_name or "").strip()
        if not normalized_tool:
            raise ValidationException(message="tool_name 不能为空", code="INVALID_TOOL_NAME")
        if not isinstance(arguments, dict):
            raise ValidationException(message="arguments 必须为 JSON Object", code="INVALID_TOOL_ARGUMENTS")

        selected_provider = self._registry.get_provider(provider)
        started = time.perf_counter()
        replay_of = self._resolve_replay_record(replay_of_id=replay_of_id)
        try:
            response = selected_provider.execute_tool(tool_name=normalized_tool, arguments=arguments)
            duration_ms = int((time.perf_counter() - started) * 1000)

            meta = {
                "provider": selected_provider.name,
                "tool": response.tool,
                "duration_ms": duration_ms,
            }
            if response.meta:
                meta.update(response.meta)
            duration_for_metrics = int(meta.get("duration_ms", duration_ms) or duration_ms)  # type: ignore[call-overload]
            fallback_used = bool(meta.get("fallback_used", False))
            observability = self._metrics.record(
                provider=selected_provider.name,
                capability=f"workbench:{response.tool}",
                success=True,
                duration_ms=duration_for_metrics,
                fallback_used=fallback_used,
            )
            meta["observability"] = observability
            masked_arguments = self._mask_payload(arguments)
            masked_data = self._mask_payload(response.data)
            masked_raw = self._mask_payload(response.raw)
            masked_meta = self._mask_payload(meta)
            payload = {
                "provider": selected_provider.name,
                "tool": response.tool,
                "arguments": masked_arguments,
                "meta": masked_meta,
                "data": masked_data,
                "raw": masked_raw,
            }
            self._store_sample(
                provider=selected_provider.name,
                tool_name=response.tool,
                data=masked_data,
                captured_at=timezone.now(),
            )
            self._create_history(
                provider=selected_provider.name,
                tool_name=response.tool,
                arguments=masked_arguments,
                response_data=masked_data,
                response_raw=masked_raw,
                response_meta=masked_meta,
                success=True,
                error_code="",
                error_message="",
                duration_ms=duration_ms,
                operator_username=actor_username,
                replay_of=replay_of,
            )
            return payload
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._metrics.record(
                provider=selected_provider.name,
                capability=f"workbench:{normalized_tool}",
                success=False,
                duration_ms=duration_ms,
                fallback_used=False,
            )
            self._create_history(
                provider=selected_provider.name,
                tool_name=normalized_tool,
                arguments=self._mask_payload(arguments),
                response_data={},
                response_raw={},
                response_meta={},
                success=False,
                error_code=type(exc).__name__,
                error_message=str(exc).strip() or type(exc).__name__,
                duration_ms=duration_ms,
                operator_username=actor_username,
                replay_of=replay_of,
            )
            raise

    def replay_execution(
        self,
        *,
        execution_id: int,
        actor_username: str = "",
        actor_is_superuser: bool = False,
    ) -> dict[str, Any]:
        self._ensure_superuser(actor_is_superuser=actor_is_superuser)
        try:
            record = McpWorkbenchExecution.objects.get(id=execution_id)
        except McpWorkbenchExecution.DoesNotExist as exc:
            raise ValidationException(
                message=f"未找到执行记录: {execution_id}",
                code="WORKBENCH_EXECUTION_NOT_FOUND",
                errors={"execution_id": execution_id},
            ) from exc

        arguments = record.arguments if isinstance(record.arguments, dict) else {}
        payload = self.execute_tool(
            provider=record.provider,
            tool_name=record.tool_name,
            arguments=arguments,
            actor_username=actor_username,
            actor_is_superuser=actor_is_superuser,
            replay_of_id=record.id,
        )
        payload["replay_of"] = record.id
        return payload

    def list_history(
        self,
        *,
        provider: str | None = None,
        tool_name: str | None = None,
        limit: int = 20,
        actor_is_superuser: bool = False,
    ) -> list[dict[str, Any]]:
        self._ensure_superuser(actor_is_superuser=actor_is_superuser)
        queryset: QuerySet[McpWorkbenchExecution] = McpWorkbenchExecution.objects.all()
        normalized_provider = str(provider or "").strip()
        if normalized_provider:
            queryset = queryset.filter(provider=normalized_provider)
        normalized_tool = str(tool_name or "").strip()
        if normalized_tool:
            queryset = queryset.filter(tool_name=normalized_tool)
        rows = queryset.order_by("-created_at")[: max(1, min(100, int(limit or 20)))]
        return [
            {
                "id": row.id,
                "provider": row.provider,
                "tool_name": row.tool_name,
                "success": row.success,
                "duration_ms": row.duration_ms,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "operator_username": row.operator_username,
                "requested_transport": row.requested_transport,
                "actual_transport": row.actual_transport,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "arguments": row.arguments if isinstance(row.arguments, dict) else {},
                "replay_of_id": row.replay_of_id,
            }
            for row in rows
        ]

    @staticmethod
    def _mask_payload(payload: Any) -> Any:
        return scrub_for_storage(payload)

    def _ensure_superuser(self, *, actor_is_superuser: bool) -> None:
        if not self._enforce_superuser:
            return
        if bool(actor_is_superuser):
            return
        raise PermissionDenied(message="仅超级管理员可使用 MCP 调试工作台", code="PERMISSION_DENIED")

    def _read_registry_int(self, method_name: str, default: int) -> int:
        getter = getattr(self._registry, method_name, None)
        if not callable(getter):
            return default
        try:
            value = int(getter() or default)
        except Exception:
            return default
        return value if value > 0 else default

    def _read_registry_float(self, method_name: str, default: float) -> float:
        getter = getattr(self._registry, method_name, None)
        if not callable(getter):
            return default
        try:
            value = float(getter() or default)
        except Exception:
            return default
        return value

    def _create_history(
        self,
        *,
        provider: str,
        tool_name: str,
        arguments: dict[str, Any],
        response_data: Any,
        response_raw: Any,
        response_meta: dict[str, Any],
        success: bool,
        error_code: str,
        error_message: str,
        duration_ms: int,
        operator_username: str,
        replay_of: McpWorkbenchExecution | None,
    ) -> None:
        if not self._persist_history:
            return

        requested_transport = str(response_meta.get("requested_transport", "") or "").strip()
        actual_transport = str(response_meta.get("transport", "") or "").strip()
        McpWorkbenchExecution.objects.create(
            provider=provider,
            tool_name=tool_name,
            arguments=arguments if isinstance(arguments, dict) else {},
            response_data=response_data if isinstance(response_data, (dict, list)) else {"value": str(response_data)},
            response_raw=response_raw if isinstance(response_raw, (dict, list)) else {"value": str(response_raw)},
            response_meta=response_meta if isinstance(response_meta, dict) else {},
            success=success,
            error_code=str(error_code or "").strip(),
            error_message=str(error_message or "").strip(),
            duration_ms=max(0, int(duration_ms or 0)),
            requested_transport=requested_transport,
            actual_transport=actual_transport,
            operator_username=str(operator_username or "").strip()[:150],
            replay_of=replay_of,
        )

    @staticmethod
    def _resolve_replay_record(*, replay_of_id: int | None) -> McpWorkbenchExecution | None:
        if not replay_of_id:
            return None
        try:
            return McpWorkbenchExecution.objects.get(id=int(replay_of_id))
        except (TypeError, ValueError, McpWorkbenchExecution.DoesNotExist):
            return None

    def _load_sample(self, *, provider: str, tool_name: str) -> dict[str, Any] | None:
        sample = cache.get(self._sample_cache_key(provider=provider, tool_name=tool_name))
        if isinstance(sample, dict):
            return sample

        record = (
            McpWorkbenchExecution.objects.filter(provider=provider, tool_name=tool_name, success=True)
            .order_by("-created_at")
            .first()
        )
        if record is None:
            return None
        sample = {
            "captured_at": record.created_at.isoformat() if record.created_at else "",
            "data": record.response_data if isinstance(record.response_data, (dict, list)) else {},
        }
        cache.set(
            self._sample_cache_key(provider=provider, tool_name=tool_name), sample, timeout=self._sample_ttl_seconds
        )
        return sample

    def _store_sample(self, *, provider: str, tool_name: str, data: Any, captured_at: datetime) -> None:
        sample = {
            "captured_at": captured_at.isoformat(),
            "data": self._truncate_data(data),
        }
        cache.set(
            self._sample_cache_key(provider=provider, tool_name=tool_name),
            sample,
            timeout=self._sample_ttl_seconds,
        )

    @staticmethod
    def _truncate_data(data: Any) -> Any:
        try:
            serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return data
        if len(serialized) <= _MAX_SAMPLE_JSON_CHARS:
            return data
        return {
            "_truncated": True,
            "preview": serialized[:_MAX_SAMPLE_JSON_CHARS],
            "original_length": len(serialized),
        }

    @staticmethod
    def _sample_cache_key(*, provider: str, tool_name: str) -> str:
        return f"mcp_workbench:sample:{provider}:{tool_name}"
