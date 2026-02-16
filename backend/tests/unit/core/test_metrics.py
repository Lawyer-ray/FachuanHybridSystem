from django.core.cache import cache

from apps.core.telemetry.metrics import Histogram, normalize_path_group, record_request, snapshot


def test_normalize_path_group_replaces_ids():
    assert normalize_path_group("/api/v1/cases/123/detail", max_segments=4) == "/api/v1/cases/:id"
    assert (
        normalize_path_group("/api/v1/exports/550e8400-e29b-41d4-a716-446655440000/download", max_segments=4)
        == "/api/v1/exports/:id"
    )


def test_histogram_quantile_uses_bucket_bounds():
    h = Histogram(buckets_ms=(10, 20, 50), counts={10: 5, 20: 3, 50: 2}, total_count=10, total_sum_ms=0)
    assert h.quantile_ms(0.5) == 10
    assert h.quantile_ms(0.8) == 20
    assert h.quantile_ms(0.99) == 50


def test_record_request_updates_snapshot():
    cache.clear()
    record_request(method="GET", path="/api/v1/health/ready", status_code=200, duration_ms=12, window_minutes=2)
    data = snapshot(window_minutes=2)
    assert data["requests"]["count"] >= 1
