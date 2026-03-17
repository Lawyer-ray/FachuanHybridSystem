"""企业数据标准化查询服务。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date
from typing import Any

from django.core.cache import cache

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService
from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry
from apps.enterprise_data.services.providers.base import EnterpriseDataProvider
from apps.enterprise_data.services.types import (
    DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
    DEFAULT_ALERT_MIN_SAMPLES,
    DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
    DEFAULT_METRICS_WINDOW_SECONDS,
    DEFAULT_RISK_TYPE,
    ProviderResponse,
)

logger = logging.getLogger(__name__)

_BIDDING_SEARCH_TYPES = {1, 2, 3}
_BIDDING_BID_TYPES = {1, 2, 4}


class EnterpriseDataService:
    """对上游 provider 输出统一的查询协议。"""

    def __init__(
        self,
        *,
        registry: EnterpriseProviderRegistry | None = None,
        metrics_service: EnterpriseDataMetricsService | None = None,
    ) -> None:
        self._registry = registry or EnterpriseProviderRegistry()
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

    def list_providers(self, *, include_tools: bool = False) -> dict[str, list[dict[str, Any]]]:
        descriptors = self._registry.list_providers()
        items: list[dict[str, Any]] = []
        for descriptor in descriptors:
            item = {
                "name": descriptor.name,
                "enabled": descriptor.enabled,
                "is_default": descriptor.is_default,
                "transport": descriptor.transport,
                "capabilities": descriptor.capabilities,
                "tools": [],
                "note": descriptor.note,
            }
            if include_tools and descriptor.enabled:
                item["tools"], item["note"] = self._resolve_provider_tools(descriptor.name)
            items.append(item)
        return {"items": items}

    def search_companies(
        self,
        *,
        keyword: str,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword:
            raise ValidationException(message="keyword 不能为空", code="INVALID_KEYWORD")
        query = {"keyword": normalized_keyword}
        return self._execute(
            capability="search_companies",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.search_companies(keyword=normalized_keyword),
        )

    def get_company_profile(
        self,
        *,
        company_id: str,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise ValidationException(message="company_id 不能为空", code="INVALID_COMPANY_ID")
        query = {"company_id": normalized_company_id}
        return self._execute(
            capability="get_company_profile",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.get_company_profile(company_id=normalized_company_id),
        )

    def get_company_risks(
        self,
        *,
        company_id: str,
        risk_type: str = DEFAULT_RISK_TYPE,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_company_id = str(company_id or "").strip()
        normalized_risk_type = str(risk_type or DEFAULT_RISK_TYPE).strip() or DEFAULT_RISK_TYPE
        if not normalized_company_id:
            raise ValidationException(message="company_id 不能为空", code="INVALID_COMPANY_ID")
        query = {"company_id": normalized_company_id, "risk_type": normalized_risk_type}
        return self._execute(
            capability="get_company_risks",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.get_company_risks(
                company_id=normalized_company_id,
                risk_type=normalized_risk_type,
            ),
        )

    def get_company_shareholders(
        self,
        *,
        company_id: str,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise ValidationException(message="company_id 不能为空", code="INVALID_COMPANY_ID")
        query = {"company_id": normalized_company_id}
        return self._execute(
            capability="get_company_shareholders",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.get_company_shareholders(company_id=normalized_company_id),
        )

    def get_company_personnel(
        self,
        *,
        company_id: str,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise ValidationException(message="company_id 不能为空", code="INVALID_COMPANY_ID")
        query = {"company_id": normalized_company_id}
        return self._execute(
            capability="get_company_personnel",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.get_company_personnel(company_id=normalized_company_id),
        )

    def get_person_profile(
        self,
        *,
        hcgid: str,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_hcgid = str(hcgid or "").strip()
        if not normalized_hcgid:
            raise ValidationException(message="hcgid 不能为空", code="INVALID_HCGID")
        query = {"hcgid": normalized_hcgid}
        return self._execute(
            capability="get_person_profile",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.get_person_profile(hcgid=normalized_hcgid),
        )

    def search_bidding_info(
        self,
        *,
        keyword: str,
        search_type: int = 1,
        bid_type: int = 4,
        start_date: date | None = None,
        end_date: date | None = None,
        provider: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword:
            raise ValidationException(message="keyword 不能为空", code="INVALID_KEYWORD")
        if search_type not in _BIDDING_SEARCH_TYPES:
            raise ValidationException(
                message=f"search_type 必须为 {sorted(_BIDDING_SEARCH_TYPES)} 之一",
                code="INVALID_SEARCH_TYPE",
            )
        if bid_type not in _BIDDING_BID_TYPES:
            raise ValidationException(
                message=f"bid_type 必须为 {sorted(_BIDDING_BID_TYPES)} 之一",
                code="INVALID_BID_TYPE",
            )
        if start_date and end_date and start_date > end_date:
            raise ValidationException(message="start_date 不能晚于 end_date", code="INVALID_DATE_RANGE")

        query: dict[str, Any] = {
            "keyword": normalized_keyword,
            "search_type": search_type,
            "bid_type": bid_type,
        }
        if start_date:
            query["start_date"] = start_date.isoformat()
        if end_date:
            query["end_date"] = end_date.isoformat()

        return self._execute(
            capability="search_bidding_info",
            provider=provider,
            query=query,
            include_raw=include_raw,
            executor=lambda selected: selected.search_bidding_info(
                keyword=normalized_keyword,
                search_type=search_type,
                bid_type=bid_type,
                start_date=(start_date.isoformat() if start_date else None),
                end_date=(end_date.isoformat() if end_date else None),
            ),
        )

    def _execute(
        self,
        *,
        capability: str,
        provider: str | None,
        query: dict[str, Any],
        include_raw: bool,
        executor: Any,
    ) -> dict[str, Any]:
        selected_provider = self._registry.get_provider(provider)
        selected_provider_name = selected_provider.name
        cache_key = self._build_cache_key(provider=selected_provider_name, capability=capability, query=query)

        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            payload = dict(cached)
            payload_meta = dict(payload.get("meta", {}))
            payload_meta["cached"] = True
            payload["meta"] = payload_meta
            if not include_raw:
                payload["raw"] = None
            return payload

        started = time.perf_counter()
        try:
            response: ProviderResponse = executor(selected_provider)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._metrics.record(
                provider=selected_provider_name,
                capability=capability,
                success=False,
                duration_ms=duration_ms,
                fallback_used=False,
            )
            raise
        payload = self._build_query_payload(
            provider=selected_provider_name,
            transport=selected_provider.transport,
            capability=capability,
            query=query,
            response=response,
            include_raw=include_raw,
        )
        measured_duration_ms = int((time.perf_counter() - started) * 1000)
        duration_ms = int(response.meta.get("duration_ms", measured_duration_ms) or measured_duration_ms)
        fallback_used = bool(response.meta.get("fallback_used", False))
        observability = self._metrics.record(
            provider=selected_provider_name,
            capability=capability,
            success=True,
            duration_ms=duration_ms,
            fallback_used=fallback_used,
        )
        payload_meta = dict(payload.get("meta", {}))
        payload_meta["observability"] = observability
        payload["meta"] = payload_meta
        cache_ttl = self._registry.get_cache_ttl_seconds()
        cache.set(cache_key, payload, timeout=cache_ttl)

        if not include_raw:
            payload = dict(payload)
            payload["raw"] = None
        return payload

    @staticmethod
    def _build_query_payload(
        *,
        provider: str,
        transport: str,
        capability: str,
        query: dict[str, Any],
        response: ProviderResponse,
        include_raw: bool,
    ) -> dict[str, Any]:
        meta = {
            "provider": provider,
            "transport": transport,
            "tool": response.tool,
            "capability": capability,
            "cached": False,
        }
        if response.meta:
            meta.update(response.meta)
        return {
            "query": query,
            "data": response.data,
            "meta": meta,
            "raw": response.raw if include_raw else None,
        }

    def _resolve_provider_tools(self, provider_name: str) -> tuple[list[str], str]:
        try:
            provider = self._registry.get_provider(provider_name)
            return provider.list_tools(), ""
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            logger.warning(
                "List provider tools failed",
                extra={
                    "provider": provider_name,
                    "error_type": type(exc).__name__,
                },
            )
            return [], f"工具探测失败: {detail}"

    @staticmethod
    def _build_cache_key(*, provider: str, capability: str, query: dict[str, Any]) -> str:
        normalized = json.dumps(
            {"provider": provider, "capability": capability, "query": query},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.md5(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"enterprise_data:{digest}"

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
