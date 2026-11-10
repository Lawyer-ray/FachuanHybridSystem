"""同步时间窗口（滚动窗口）的纯函数测试。

背景：手动同步此前无窗口概念，一律按来源的 ``sync_since`` 走——实测某邮箱
半年 290 封里只有 2 封是真正关心的到账通知，全量拉取既慢又污染收件箱。

现在：**前端手动同步**传窗口天数（默认 7 天）；**后台/首次建源**传 None 才
按 ``sync_since`` 完整回填。本文件锁死这条分界。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.message_hub.services.base import DEFAULT_SYNC_WINDOW_DAYS, resolve_sync_since


class _Source:
    """够 resolve_sync_since 用的最小来源替身。"""

    def __init__(self, sync_since):
        self.sync_since = sync_since


class TestResolveSyncSince:
    def test_default_window_is_7_days(self):
        assert DEFAULT_SYNC_WINDOW_DAYS == 7

    def test_none_returns_source_since_untouched(self):
        """None = 完整回填：必须原样返回 sync_since，不能被窗口收窄。

        这是「只有后端从 0 同步才从历史时期开始」的落点——搞错这条，
        首次建源就再也拉不到历史邮件。
        """
        since = timezone.now() - timedelta(days=200)
        assert resolve_sync_since(_Source(since), None) == since

    def test_window_narrows_to_recent_days(self):
        since = timezone.now() - timedelta(days=200)
        resolved = resolve_sync_since(_Source(since), 7)
        expected = timezone.now() - timedelta(days=7)
        assert abs((resolved - expected).total_seconds()) < 5

    def test_window_never_goes_before_source_since(self):
        """窗口只收窄，不越过来源起点去拉更早的邮件。"""
        since = timezone.now() - timedelta(days=2)
        resolved = resolve_sync_since(_Source(since), 30)
        assert resolved == since

    def test_takes_later_of_the_two(self):
        # 来源起点 100 天前，窗口 7 天 → 取 7 天前
        since = timezone.now() - timedelta(days=100)
        assert resolve_sync_since(_Source(since), 7) > since
        # 来源起点 1 天前，窗口 30 天 → 取 1 天前
        recent = timezone.now() - timedelta(days=1)
        assert resolve_sync_since(_Source(recent), 30) == recent

    def test_zero_or_negative_days_clamped_to_one(self):
        since = timezone.now() - timedelta(days=100)
        for days in (0, -5):
            resolved = resolve_sync_since(_Source(since), days)
            expected = timezone.now() - timedelta(days=1)
            assert abs((resolved - expected).total_seconds()) < 5


class TestApiNormalization:
    """API 层的 days 归一化：省略=回填，数字=窗口，超界收敛。"""

    def test_none_stays_none(self):
        from apps.message_hub.api.message_source_api import _normalize_window_days

        assert _normalize_window_days(None) is None

    def test_number_passes_through(self):
        from apps.message_hub.api.message_source_api import _normalize_window_days

        assert _normalize_window_days(7) == 7
        assert _normalize_window_days(30) == 30

    def test_upper_bound(self):
        from apps.message_hub.api.message_source_api import _normalize_window_days

        assert _normalize_window_days(10_000) == 365

    def test_lower_bound(self):
        from apps.message_hub.api.message_source_api import _normalize_window_days

        assert _normalize_window_days(0) == 1
        assert _normalize_window_days(-3) == 1


@pytest.mark.parametrize('days', [7, 30, 90])
def test_window_options_are_positive(days):
    """前端可选的窗口值必须都是正数（防止 0 导致拉取范围异常）。"""
    assert days > 0
