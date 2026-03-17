from __future__ import annotations

import uuid

from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService


def test_metrics_service_aggregates_success_failure_latency_and_fallback() -> None:
    capability = f"search_companies_{uuid.uuid4().hex[:8]}"
    service = EnterpriseDataMetricsService(window_seconds=300, alert_min_samples=2)

    service.record(
        provider="tianyancha",
        capability=capability,
        success=True,
        duration_ms=100,
        fallback_used=False,
    )
    snapshot = service.record(
        provider="tianyancha",
        capability=capability,
        success=False,
        duration_ms=900,
        fallback_used=True,
    )

    assert snapshot["total"] == 2
    assert snapshot["success"] == 1
    assert snapshot["failure"] == 1
    assert snapshot["fallback"] == 1
    assert snapshot["avg_duration_ms"] == 500
    assert snapshot["success_rate"] == 0.5
    assert snapshot["fallback_rate"] == 0.5
