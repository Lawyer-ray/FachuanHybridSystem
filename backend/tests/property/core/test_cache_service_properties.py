"""
缓存服务属性测试

# Feature: backend-quality-to-10, Property 8: 缓存修改后失效（Round-Trip）
# Feature: backend-quality-to-10, Property 9: 缓存降级不抛异常
Validates: Requirements 6.3, 6.5
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.cache_service import cached, invalidate_cache


# ---------------------------------------------------------------------------
# Property 8: 缓存修改后失效（Round-Trip）
# ---------------------------------------------------------------------------


class TestCacheInvalidationAfterModifyProperty:
    """
    Property 8: 缓存修改后失效（Round-Trip）

    # Feature: backend-quality-to-10, Property 8: 缓存修改后失效（Round-Trip）
    Validates: Requirements 6.3
    """

    @given(
        key=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_:"),
        ),  # noqa: E501
        value1=st.integers(),
        value2=st.integers(),
    )
    @settings(max_examples=100)
    def test_invalidate_then_refetch_returns_new_value(self, key: str, value1: int, value2: int) -> None:
        """
        Property 8: 写入缓存 → 失效 → 再次查询应返回新值而非旧值。

        # Feature: backend-quality-to-10, Property 8: 缓存修改后失效（Round-Trip）
        Validates: Requirements 6.3
        """
        store: dict[str, Any] = {}

        def fake_get(k: str) -> Any:
            return store.get(k)

        def fake_set(k: str, v: Any, timeout: Any = None) -> None:
            store[k] = v

        def fake_delete(k: str) -> None:
            store.pop(k, None)

        with patch("apps.core.cache_service.cache") as mock_cache:
            mock_cache.get.side_effect = fake_get
            mock_cache.set.side_effect = fake_set
            mock_cache.delete.side_effect = fake_delete

            call_count = 0

            @cached(key, timeout=60)
            def fetch(**kwargs: Any) -> int:
                nonlocal call_count
                call_count += 1
                return value1 if call_count == 1 else value2

            # 第一次调用：缓存未命中，写入 value1
            result1 = fetch()
            assert result1 == value1

            # 失效缓存
            invalidate_cache(key)
            assert key not in store

            # 第二次调用：缓存已失效，应返回 value2（新值）
            result2 = fetch()
            assert result2 == value2
            assert result2 != result1 or value1 == value2


# ---------------------------------------------------------------------------
# Property 9: 缓存降级不抛异常
# ---------------------------------------------------------------------------


class TestCacheFallbackNoExceptionProperty:
    """
    Property 9: 缓存降级不抛异常

    # Feature: backend-quality-to-10, Property 9: 缓存降级不抛异常
    Validates: Requirements 6.5
    """

    @given(
        key=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_:"),
        ),  # noqa: E501
        expected=st.integers(),
    )
    @settings(max_examples=100)
    def test_cache_read_failure_falls_back_to_db(self, key: str, expected: int) -> None:
        """
        Property 9: cache.get 抛异常时，cached 装饰器应降级直接调用原函数，不抛出异常。

        # Feature: backend-quality-to-10, Property 9: 缓存降级不抛异常
        Validates: Requirements 6.5
        """
        with patch("apps.core.cache_service.cache") as mock_cache:
            mock_cache.get.side_effect = ConnectionError("Redis 不可用")
            mock_cache.set.side_effect = ConnectionError("Redis 不可用")

            @cached(key, timeout=60)
            def fetch(**kwargs: Any) -> int:
                return expected

            # 不应抛出任何异常，应返回原函数结果
            result = fetch()
            assert result == expected

    @given(
        key=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_:"),
        ),  # noqa: E501
    )
    @settings(max_examples=100)
    def test_invalidate_cache_failure_does_not_raise(self, key: str) -> None:
        """
        Property 9: cache.delete 抛异常时，invalidate_cache 不应抛出异常。

        # Feature: backend-quality-to-10, Property 9: 缓存降级不抛异常
        Validates: Requirements 6.5
        """
        with patch("apps.core.cache_service.cache") as mock_cache:
            mock_cache.delete.side_effect = ConnectionError("Redis 不可用")

            # 不应抛出任何异常
            invalidate_cache(key)
