"""validate_runtime_topology / resolve_web_worker_count 拓扑守卫单测。

覆盖：debug 放行 / 单进程无 Redis（WARNING）/ 多进程无 Redis（RuntimeError）/
逃生口豁免（WARNING）/ worker 计数合并三个环境变量。
"""

from __future__ import annotations

import pytest

from apps.core.config.django_runtime import resolve_web_worker_count, validate_runtime_topology

_LOCMEM = "django.core.cache.backends.locmem.LocMemCache"
_REDIS_CACHE = "django.core.cache.backends.redis.RedisCache"
_INMEM_CHANNEL = "channels.layers.InMemoryChannelLayer"
_REDIS_CHANNEL = "channels_redis.core.RedisChannelLayer"


def _validate(**overrides):
    kwargs = dict(
        debug=False,
        web_workers=1,
        q_workers=1,
        cache_backend=_LOCMEM,
        channel_backend=_INMEM_CHANNEL,
        redis_cache_configured=False,
        redis_channel_configured=False,
    )
    kwargs.update(overrides)
    return validate_runtime_topology(**kwargs)


class TestDebugBypass:
    def test_debug_returns_empty(self):
        assert _validate(debug=True, web_workers=8, q_workers=8) == []


class TestRedisConfigured:
    def test_multiprocess_with_redis_passes(self):
        assert _validate(web_workers=4, redis_cache_configured=True, redis_channel_configured=True) == []


class TestSingleProcessNoRedis:
    def test_warns_but_does_not_fail(self):
        warnings = _validate()
        assert len(warnings) == 2
        assert any("LocMemCache" in w for w in warnings)
        assert any("channel layer" in w for w in warnings)

    def test_channel_redis_configured_only_warns_cache(self):
        warnings = _validate(redis_channel_configured=True, channel_backend=_REDIS_CHANNEL)
        assert len(warnings) == 1
        assert "LocMemCache" in warnings[0]


class TestMultiprocessNoRedis:
    def test_web_workers_trigger_runtime_error(self):
        with pytest.raises(RuntimeError, match="LocMemCache"):
            _validate(web_workers=4)

    def test_q_workers_trigger_runtime_error(self):
        with pytest.raises(RuntimeError, match="InMemoryChannelLayer"):
            _validate(q_workers=8, cache_backend=_REDIS_CACHE, redis_cache_configured=True)

    def test_escape_hatch_downgrades_to_warning(self, monkeypatch):
        monkeypatch.setenv("DJANGO_ALLOW_LOCMEM_CACHE", "true")
        warnings = _validate(web_workers=4)
        assert len(warnings) == 2
        assert any("显式豁免" in w or "放行" in w for w in warnings)


class TestResolveWebWorkerCount:
    def test_default_one(self, monkeypatch):
        for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
            monkeypatch.delenv(name, raising=False)
        assert resolve_web_worker_count() == 1

    def test_merges_all_signals_takes_max(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "2")
        monkeypatch.setenv("UVICORN_WORKERS", "4")
        monkeypatch.setenv("GUNICORN_WORKERS", "3")
        assert resolve_web_worker_count() == 4

    def test_uvicorn_default_signal_detected(self, monkeypatch):
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        monkeypatch.setenv("UVICORN_WORKERS", "4")
        assert resolve_web_worker_count() == 4

    def test_invalid_values_ignored(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "abc")
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        assert resolve_web_worker_count() == 1

    def test_zero_clamped_to_one(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "0")
        assert resolve_web_worker_count() == 1
