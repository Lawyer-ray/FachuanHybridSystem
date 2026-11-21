"""跨进程的 Key 健康记账与配置代次（2026-11-21 审计 P0-2 / P1-6 / S4）。

## 守的是什么

生产是 `2 worker + 1 共享 MCP`，而 Key 冷却与配置缓存原本**只在进程内**：

1. worker A 里被判 401 的 Key，worker B 与 MCP 完全不知道 → 反复选中、反复吃 401；
2. Admin 换 Key 只清「保存的那个 worker」的缓存，其它进程要等 TTL（原来 300 秒）
   → 症状是「聊天好了、检索还用旧 Key」。

修复用的是 Django cache（配 Redis 即全局、否则 LocMem 等价于今天的行为），
并且**一律 fail-open**：缓存读失败必须当「健康/未变更」，否则一次 Redis 抖动
会把整个 Key 池判死。
"""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache


from apps.core.llm import key_health
from apps.core.llm.key_pool import KeyPool
from apps.core.llm.key_selector import select_key
from apps.core.services.llm_provider_service import LLMProviderService


class _GatewayError(Exception):
    """模拟网关 502（属于「Key 侧/网关侧」失败，应当冷却）。"""

    status_code = 502


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    cache.clear()
    LLMProviderService._cache = None
    yield
    cache.clear()
    LLMProviderService._cache = None


class TestKeyHealthStore:
    def test_mark_then_read(self) -> None:
        key_health.mark_cooling("律所 kimi", "sk-abc", 60, "429 限流")

        health = key_health.get_health("律所 kimi", "sk-abc")

        assert health.cooling is True
        assert 0 < health.remaining <= 60
        assert health.reason == "429 限流"

    def test_unknown_key_is_healthy(self) -> None:
        assert key_health.get_health("律所 kimi", "sk-other").cooling is False

    def test_clear_restores_health(self) -> None:
        key_health.mark_cooling("p", "k", 60, "x")
        key_health.clear_cooling("p", "k")
        assert key_health.get_health("p", "k").cooling is False

    def test_expired_entry_reads_healthy(self) -> None:
        key_health.mark_cooling("p", "k", 1, "x")
        # 直接把缓存里那条改成已过期（不让用例真的睡 1 秒）
        cache.set(
            key_health._health_key("p", "k"),
            {"until": time.time() - 1, "reason": "x"},
            timeout=60,
        )
        assert key_health.get_health("p", "k").cooling is False

    def test_cooling_map_only_returns_cooling(self) -> None:
        key_health.mark_cooling("p", "k1", 60, "x")

        mapping = key_health.cooling_map("p", ["k1", "k2"])

        assert set(mapping) == {"k1"}

    def test_cache_keys_are_memcached_safe(self) -> None:
        """平台名是中文时不能直接把中文拼进缓存键——Django 会抛 CacheKeyWarning。"""
        segment = key_health._safe_provider_segment("律所 kimi")

        assert segment.isascii()
        assert " " not in segment
        assert segment.startswith("__")

    def test_fail_open_when_cache_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Broken:
            def get(self, *a: object, **k: object) -> None:
                raise RuntimeError("redis down")

            def get_many(self, *a: object, **k: object) -> None:
                raise RuntimeError("redis down")

            def set(self, *a: object, **k: object) -> None:
                raise RuntimeError("redis down")

            def delete(self, *a: object, **k: object) -> None:
                raise RuntimeError("redis down")

        monkeypatch.setattr(key_health, "_cache", lambda: _Broken())

        # 读失败 = 健康（fail-open）；写失败 = 静默（不阻断调用）
        assert key_health.get_health("p", "k").cooling is False
        assert key_health.cooling_map("p", ["k"]) == {}
        key_health.mark_cooling("p", "k", 60, "x")
        key_health.clear_cooling("p", "k")


class TestSelectorSkipsCoolingKeys:
    def test_skips_cooling_key(self) -> None:
        key_health.mark_cooling("p", "k1", 60, "x")

        picked = {select_key(["k1", "k2"], provider="p") for _ in range(20)}

        assert picked == {"k2"}, "冷却中的 Key 不该被选中"

    def test_falls_back_when_everything_cooling(self) -> None:
        key_health.mark_cooling("p", "k1", 60, "x")
        key_health.mark_cooling("p", "k2", 60, "x")

        # fail-open：宁可发一个可能 429 的请求，也不要让提问卡在「没有可用 Key」
        assert select_key(["k1", "k2"], provider="p") in {"k1", "k2"}

    def test_without_provider_name_keeps_old_behaviour(self) -> None:
        key_health.mark_cooling("p", "k1", 60, "x")

        picked = {select_key(["k1", "k2"]) for _ in range(20)}

        assert picked == {"k1", "k2"}, "拿不到平台名时不做半吊子过滤"

    def test_empty_keys(self) -> None:
        assert select_key([], provider="p") == ""


class TestPoolSharesHealthAcrossInstances:
    def test_cooldown_visible_to_other_pool_instance(self) -> None:
        """模拟两个进程/两个池实例：A 判死，B 必须也能看见并跳过它。"""
        importers = KeyPool(["k1"], concurrency_per_key=3, provider="p")
        for _ in range(KeyPool.FAILS_BEFORE_COOLDOWN):
            idx = importers.acquire("m")
            assert idx is not None
            importers.release(idx, success=False, model="m", error=_GatewayError("boom"))
        assert importers.is_cooling(0, "m") is True

        other_process = KeyPool(["k1", "k2"], concurrency_per_key=3, provider="p")
        picked = set()
        for _ in range(10):
            idx = other_process.acquire("m")
            assert idx is not None
            picked.add(idx)
            other_process.release(idx, success=True, model="m")

        assert picked == {1}, "另一个进程应当只看到 k2（k1 在共享冷却中）"

    def test_success_clears_shared_health(self) -> None:
        pool = KeyPool(["k1"], concurrency_per_key=3, provider="p")
        for _ in range(KeyPool.FAILS_BEFORE_COOLDOWN):
            idx = pool.acquire("m")
            pool.release(idx or 0, success=False, model="m", error=_GatewayError("boom"))
        assert pool.is_cooling(0, "m") is True

        pool.release(pool.acquire("m") or 0, success=True, model="m")

        assert key_health.get_health("p", "k1").cooling is False


class TestConfigGeneration:
    def test_bump_changes_generation(self) -> None:
        first = key_health.config_generation()
        bumped = key_health.bump_config_generation()

        assert bumped == first + 1
        assert key_health.config_generation() == bumped

    def test_provider_service_invalidate_bumps_generation(self) -> None:
        before = key_health.config_generation()

        LLMProviderService.invalidate_cache()

        assert key_health.config_generation() == before + 1

    def test_other_process_generation_change_invalidates_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """别的进程 bump 代次后，本进程下一次取配置必须重载（不等 TTL）。"""
        calls: list[int] = []

        monkeypatch.setattr(LLMProviderService, "_load_from_db", classmethod(lambda cls: calls.append(1) or []))
        LLMProviderService.get_providers()
        assert len(calls) == 1
        LLMProviderService.get_providers()
        assert len(calls) == 1, "同进程同代次应命中缓存"

        key_health.bump_config_generation()  # 模拟另一个 worker 保存了配置

        LLMProviderService.get_providers()
        assert len(calls) == 2, "代次变了必须重载"

    def test_read_failure_is_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """读库失败不得把「没有平台」缓存下来（审计 P1-7）。"""
        attempts: list[int] = []

        def _boom(cls: object) -> list[object]:
            attempts.append(1)
            raise RuntimeError("db down")

        monkeypatch.setattr(LLMProviderService, "_load_from_db", classmethod(_boom))

        assert LLMProviderService.get_providers() == []
        assert LLMProviderService.get_providers() == []
        assert len(attempts) == 2, "失败不该进缓存"
