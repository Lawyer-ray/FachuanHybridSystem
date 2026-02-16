from unittest.mock import Mock

from apps.automation.services.token.cache_manager import TokenCacheManager


def test_get_cached_token_records_cache_error_metric(monkeypatch):
    manager = TokenCacheManager()
    calls = []

    def fake_record_cache_result(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("apps.automation.services.token.cache_manager.record_cache_result", fake_record_cache_result)

    def boom(*args, **kwargs):
        raise RuntimeError("cache down")

    monkeypatch.setattr("apps.automation.services.token.cache_manager.cache.get", boom)

    assert manager.get_cached_token("site", "user@example.com") is None
    assert calls and calls[0]["result"] == "error"
