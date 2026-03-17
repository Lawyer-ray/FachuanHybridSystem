"""企业数据调用指标聚合与告警。"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache

from apps.enterprise_data.services.types import (
    DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
    DEFAULT_ALERT_MIN_SAMPLES,
    DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
    DEFAULT_METRICS_WINDOW_SECONDS,
)

logger = logging.getLogger(__name__)


class EnterpriseDataMetricsService:
    """基于缓存的窗口指标聚合器。"""

    def __init__(
        self,
        *,
        window_seconds: int = DEFAULT_METRICS_WINDOW_SECONDS,
        alert_min_samples: int = DEFAULT_ALERT_MIN_SAMPLES,
        alert_success_rate_threshold: float = DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
        alert_fallback_rate_threshold: float = DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
        alert_avg_latency_ms_threshold: int = DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    ) -> None:
        self._window_seconds = max(60, int(window_seconds or DEFAULT_METRICS_WINDOW_SECONDS))
        self._alert_min_samples = max(1, int(alert_min_samples or DEFAULT_ALERT_MIN_SAMPLES))
        self._alert_success_rate_threshold = float(
            max(0.01, min(1.0, alert_success_rate_threshold or DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD))
        )
        self._alert_fallback_rate_threshold = float(
            max(0.0, min(1.0, alert_fallback_rate_threshold or DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD))
        )
        self._alert_avg_latency_ms_threshold = max(100, int(alert_avg_latency_ms_threshold or 100))

    def record(
        self,
        *,
        provider: str,
        capability: str,
        success: bool,
        duration_ms: int,
        fallback_used: bool,
    ) -> dict[str, Any]:
        now = int(time.time())
        key = self._bucket_key(provider=provider, capability=capability)
        bucket = cache.get(key)
        if not isinstance(bucket, dict) or now - int(bucket.get("window_start", 0) or 0) >= self._window_seconds:
            bucket = self._new_bucket(now)

        bucket["total"] = int(bucket.get("total", 0) or 0) + 1
        if success:
            bucket["success"] = int(bucket.get("success", 0) or 0) + 1
        else:
            bucket["failure"] = int(bucket.get("failure", 0) or 0) + 1
        if fallback_used:
            bucket["fallback"] = int(bucket.get("fallback", 0) or 0) + 1
        bucket["duration_sum_ms"] = int(bucket.get("duration_sum_ms", 0) or 0) + max(0, int(duration_ms or 0))
        bucket["updated_at"] = now

        cache.set(key, bucket, timeout=max(self._window_seconds * 3, 600))
        snapshot = self._snapshot_from_bucket(bucket)
        self._maybe_alert(provider=provider, capability=capability, snapshot=snapshot)
        return snapshot

    def snapshot(self, *, provider: str, capability: str) -> dict[str, Any] | None:
        bucket = cache.get(self._bucket_key(provider=provider, capability=capability))
        if not isinstance(bucket, dict):
            return None
        return self._snapshot_from_bucket(bucket)

    def _maybe_alert(self, *, provider: str, capability: str, snapshot: dict[str, Any]) -> None:
        total = int(snapshot.get("total", 0) or 0)
        if total < self._alert_min_samples:
            return

        success_rate = float(snapshot.get("success_rate", 1.0) or 1.0)
        fallback_rate = float(snapshot.get("fallback_rate", 0.0) or 0.0)
        avg_latency_ms = int(snapshot.get("avg_duration_ms", 0) or 0)

        if success_rate < self._alert_success_rate_threshold:
            self._emit_alert(
                provider=provider,
                capability=capability,
                metric="success_rate",
                message=f"企业数据调用成功率过低: {success_rate:.2%}",
                snapshot=snapshot,
            )
        if fallback_rate > self._alert_fallback_rate_threshold:
            self._emit_alert(
                provider=provider,
                capability=capability,
                metric="fallback_rate",
                message=f"企业数据回退比例过高: {fallback_rate:.2%}",
                snapshot=snapshot,
            )
        if avg_latency_ms > self._alert_avg_latency_ms_threshold:
            self._emit_alert(
                provider=provider,
                capability=capability,
                metric="avg_latency_ms",
                message=f"企业数据平均耗时过高: {avg_latency_ms}ms",
                snapshot=snapshot,
            )

    def _emit_alert(
        self,
        *,
        provider: str,
        capability: str,
        metric: str,
        message: str,
        snapshot: dict[str, Any],
    ) -> None:
        alert_key = (
            f"enterprise_data:metrics_alert:{provider}:{capability}:{metric}:{int(snapshot.get('window_start_epoch', 0))}"
        )
        if not cache.add(alert_key, "1", timeout=max(60, self._window_seconds)):
            return
        logger.warning(
            message,
            extra={
                "provider": provider,
                "capability": capability,
                "metric": metric,
                "snapshot": snapshot,
            },
        )

    def _snapshot_from_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        total = max(0, int(bucket.get("total", 0) or 0))
        success = max(0, int(bucket.get("success", 0) or 0))
        failure = max(0, int(bucket.get("failure", 0) or 0))
        fallback = max(0, int(bucket.get("fallback", 0) or 0))
        duration_sum_ms = max(0, int(bucket.get("duration_sum_ms", 0) or 0))
        avg_duration_ms = int(duration_sum_ms / total) if total > 0 else 0
        success_rate = float(success / total) if total > 0 else 1.0
        fallback_rate = float(fallback / total) if total > 0 else 0.0
        return {
            "window_seconds": self._window_seconds,
            "window_start_epoch": int(bucket.get("window_start", 0) or 0),
            "window_end_epoch": int(bucket.get("window_end", 0) or 0),
            "total": total,
            "success": success,
            "failure": failure,
            "fallback": fallback,
            "avg_duration_ms": avg_duration_ms,
            "success_rate": round(success_rate, 4),
            "fallback_rate": round(fallback_rate, 4),
        }

    def _new_bucket(self, now: int) -> dict[str, int]:
        return {
            "window_start": now,
            "window_end": now + self._window_seconds,
            "total": 0,
            "success": 0,
            "failure": 0,
            "fallback": 0,
            "duration_sum_ms": 0,
            "updated_at": now,
        }

    @staticmethod
    def _bucket_key(*, provider: str, capability: str) -> str:
        return f"enterprise_data:metrics:{provider}:{capability}"
