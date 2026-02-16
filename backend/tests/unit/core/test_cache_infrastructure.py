import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.automation.services.token.performance_monitor import PerformanceMonitor
from apps.core.infrastructure import (
    CacheKeys,
    CacheTimeout,
    bump_cache_version,
    invalidate_user_access_context,
    invalidate_users_access_context,
)


@pytest.mark.django_db
def test_invalidate_user_access_context_deletes_expected_keys():
    user_id = 1001
    cache.set(CacheKeys.user_org_access(user_id), {"x": 1}, timeout=CacheTimeout.get_long())
    cache.set(CacheKeys.case_access_grants(user_id), {"y": 2}, timeout=CacheTimeout.get_long())

    invalidate_user_access_context(user_id)

    assert cache.get(CacheKeys.user_org_access(user_id)) is None
    assert cache.get(CacheKeys.case_access_grants(user_id)) is None


@pytest.mark.django_db
def test_invalidate_users_access_context_deletes_many():
    user_ids = [2001, 2002, 2003]
    for uid in user_ids:
        cache.set(CacheKeys.user_org_access(uid), {"uid": uid}, timeout=CacheTimeout.get_long())

    invalidate_users_access_context(user_ids, org_access=True, case_grants=False)

    for uid in user_ids:
        assert cache.get(CacheKeys.user_org_access(uid)) is None


@pytest.mark.django_db
def test_bump_cache_version_increments():
    key = "test:version:key"
    cache.delete(key)

    v1 = bump_cache_version(key, timeout=CacheTimeout.get_day())
    v2 = bump_cache_version(key, timeout=CacheTimeout.get_day())

    assert v2 == v1 + 1
    assert cache.get(key) == v2


@pytest.mark.django_db
def test_cachetimeout_until_end_of_day_returns_positive():
    now = timezone.now()
    ttl = CacheTimeout.until_end_of_day(now=now, buffer_seconds=0)
    assert ttl > 0
    assert ttl <= 86400


@pytest.mark.django_db
def test_token_performance_monitor_uses_bucketed_keys():
    monitor = PerformanceMonitor()
    acquisition_id = "acq-test-1"

    monitor.record_acquisition_start(acquisition_id, site_name="demo", account="acc")
    monitor.record_acquisition_end(acquisition_id, success=False, duration=1.0, error_type="timeout")

    date = timezone.localdate().strftime("%Y%m%d")
    total_key = CacheKeys.automation_token_perf_counter(date=date, site_name="demo", metric="total")
    timeout_key = CacheKeys.automation_token_perf_counter(date=date, site_name="demo", metric="timeout")

    assert int(cache.get(total_key) or 0) >= 1
    assert int(cache.get(timeout_key) or 0) >= 1
