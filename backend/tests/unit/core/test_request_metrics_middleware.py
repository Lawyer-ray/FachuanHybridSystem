import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import RequestMetricsMiddleware


@pytest.mark.unit
def test_request_metrics_skips_in_debug_when_env_disabled(settings, monkeypatch):
    settings.DEBUG = True
    monkeypatch.delenv("DJANGO_REQUEST_METRICS", raising=False)

    called: list[tuple[str, str, int, int]] = []

    from apps.core.telemetry import metrics as metrics_module

    def record_request(*, method: str, path: str, status_code: int, duration_ms: int, window_minutes: int = 10):
        called.append((method, path, status_code, duration_ms))

    monkeypatch.setattr(metrics_module, "record_request", record_request)

    middleware = RequestMetricsMiddleware(lambda _req: HttpResponse("ok", status=200))
    request = RequestFactory().get("/api/v1/health/live")
    response = middleware(request)

    assert response.status_code == 200
    assert called == []


@pytest.mark.unit
def test_request_metrics_records_in_production_by_default(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.delenv("DJANGO_REQUEST_METRICS", raising=False)

    called: list[tuple[str, str, int]] = []

    from apps.core.telemetry import metrics as metrics_module

    def record_request(*, method: str, path: str, status_code: int, duration_ms: int, window_minutes: int = 10):
        called.append((method, path, status_code))

    monkeypatch.setattr(metrics_module, "record_request", record_request)

    middleware = RequestMetricsMiddleware(lambda _req: HttpResponse("ok", status=201))
    request = RequestFactory().post("/api/v1/health", data={})
    response = middleware(request)

    assert response.status_code == 201
    assert called and called[0][:3] == ("POST", "/api/v1/health", 201)


@pytest.mark.unit
def test_request_metrics_records_in_debug_when_env_enabled(settings, monkeypatch):
    settings.DEBUG = True
    monkeypatch.setenv("DJANGO_REQUEST_METRICS", "1")

    called: list[int] = []

    from apps.core.telemetry import metrics as metrics_module

    def record_request(*, method: str, path: str, status_code: int, duration_ms: int, window_minutes: int = 10):
        called.append(status_code)

    monkeypatch.setattr(metrics_module, "record_request", record_request)

    def boom(_req):
        raise RuntimeError("boom")

    middleware = RequestMetricsMiddleware(boom)
    request = RequestFactory().get("/api/v1/boom")

    with pytest.raises(RuntimeError):
        middleware(request)

    assert called == [500]
