import threading

import pytest

from apps.core.infrastructure.request_context import get_request_id
from apps.core.middleware_request_id import RequestIdMiddleware


class DummyRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


class DummyResponse:
    def __init__(self):
        self.headers = {}

    def __setitem__(self, key, value):
        self.headers[key] = value


class HeaderlessResponse:
    def __init__(self):
        self.items: dict[str, str] = {}

    def __setitem__(self, key, value):
        self.items[key] = value


class BrokenHeaderResponse:
    def __init__(self):
        class _BrokenHeaders(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("no headers")

        self.headers = _BrokenHeaders()

    def __setitem__(self, key, value):
        raise RuntimeError("no mapping")


@pytest.mark.unit
def test_request_id_middleware_sets_request_id_and_response_header():
    captured = {}

    def get_response(request):
        captured["request_attr"] = getattr(request, "request_id", None)
        captured["context_request_id"] = get_request_id(fallback_generate=False)
        return DummyResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={"X-Request-ID": "rid-123"})
    response = middleware(request)  # type: ignore[arg-type]

    assert captured["request_attr"] == "rid-123"
    assert captured["context_request_id"] == "rid-123"
    assert response.headers["X-Request-ID"] == "rid-123"
    assert get_request_id(fallback_generate=False) is None
    assert getattr(threading.current_thread(), "request_id", None) is None


@pytest.mark.unit
def test_request_id_middleware_generates_request_id_when_missing():
    captured = {}

    def get_response(_request):
        captured["context_request_id"] = get_request_id(fallback_generate=False)
        return DummyResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={})
    response = middleware(request)  # type: ignore[arg-type]

    assert captured["context_request_id"]
    assert response.headers["X-Request-ID"] == captured["context_request_id"]


@pytest.mark.unit
def test_request_id_middleware_rejects_invalid_request_id():
    captured = {}

    def get_response(_request):
        captured["context_request_id"] = get_request_id(fallback_generate=False)
        return DummyResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={"X-Request-ID": "rid-<>-too-long-" + ("x" * 200)})
    response = middleware(request)  # type: ignore[arg-type]

    assert captured["context_request_id"]
    assert response.headers["X-Request-ID"] == captured["context_request_id"]


@pytest.mark.unit
def test_request_id_middleware_sets_and_clears_trace_id_thread_attrs():
    captured = {}

    def get_response(request):
        captured["thread_request_id"] = getattr(threading.current_thread(), "request_id", None)
        captured["thread_trace_id"] = getattr(threading.current_thread(), "trace_id", None)
        captured["context_request_id"] = get_request_id(fallback_generate=False)
        return DummyResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={"X-Request-ID": "rid-abc"})
    _response = middleware(request)  # type: ignore[arg-type]

    assert captured["context_request_id"] == "rid-abc"
    assert captured["thread_request_id"] == "rid-abc"
    assert captured["thread_trace_id"] == "rid-abc"
    assert get_request_id(fallback_generate=False) is None
    assert not hasattr(threading.current_thread(), "request_id")
    assert not hasattr(threading.current_thread(), "trace_id")


@pytest.mark.unit
def test_request_id_middleware_does_not_leak_between_threads():
    from concurrent.futures import ThreadPoolExecutor

    barrier = threading.Barrier(2, timeout=3)
    captures: dict[str, tuple[str | None, str | None, str | None]] = {}

    def run_in_thread(rid: str) -> bool:
        def get_response(_request):
            captures[rid] = (
                get_request_id(fallback_generate=False),
                getattr(threading.current_thread(), "request_id", None),
                getattr(threading.current_thread(), "trace_id", None),
            )
            barrier.wait(timeout=3)
            return DummyResponse()

        middleware = RequestIdMiddleware(get_response)
        req = DummyRequest(headers={"X-Request-ID": rid})
        _resp = middleware(req)  # type: ignore[arg-type]
        return (not hasattr(threading.current_thread(), "request_id")) and (
            not hasattr(threading.current_thread(), "trace_id")
        )

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(run_in_thread, "rid-t1")
        f2 = ex.submit(run_in_thread, "rid-t2")
        ok1 = f1.result(timeout=5)
        ok2 = f2.result(timeout=5)

    assert captures["rid-t1"] == ("rid-t1", "rid-t1", "rid-t1")
    assert captures["rid-t2"] == ("rid-t2", "rid-t2", "rid-t2")
    assert ok1 is True
    assert ok2 is True


@pytest.mark.unit
def test_request_id_middleware_falls_back_to_response_mapping_when_no_headers():
    captured = {}

    def get_response(_request):
        captured["context_request_id"] = get_request_id(fallback_generate=False)
        return HeaderlessResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={"X-Request-ID": "rid-map"})
    response = middleware(request)  # type: ignore[arg-type]

    assert captured["context_request_id"] == "rid-map"
    assert response.items["X-Request-ID"] == "rid-map"  # type: ignore[index]


@pytest.mark.unit
def test_request_id_middleware_silently_ignores_header_set_failures():
    def get_response(_request):
        return BrokenHeaderResponse()

    middleware = RequestIdMiddleware(get_response)
    request = DummyRequest(headers={"X-Request-ID": "rid-broken"})
    response = middleware(request)  # type: ignore[arg-type]

    assert isinstance(response, BrokenHeaderResponse)
