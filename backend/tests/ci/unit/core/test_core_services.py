"""
核心服务层测试：覆盖 CacheKeys、CacheTimeout、RateLimiter、EvidenceService、CaseSearchQueryBuilder。
"""

from __future__ import annotations

import datetime
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory


# =====================================================================
# CacheKeys 缓存键生成
# =====================================================================


class TestCacheKeys:
    """CacheKeys 的各方法应生成正确的缓存键。"""

    def test_user_org_access(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.user_org_access(42) == "user:org_access:42"

    def test_user_teams(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.user_teams(7) == "user:teams:7"

    def test_case_access_grants(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.case_access_grants(99) == "case:access_grants:99"

    def test_court_token_account_is_hashed(self) -> None:
        """court_token 的 account 不应以明文出现在 key 中。"""
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.court_token("法院网", "my_account")
        assert "my_account" not in key
        assert "法院网" in key or "empty" not in key

    def test_court_token_deterministic(self) -> None:
        """相同输入应生成相同的 key。"""
        from apps.core.infrastructure.cache import CacheKeys
        key1 = CacheKeys.court_token("site_a", "user_b")
        key2 = CacheKeys.court_token("site_a", "user_b")
        assert key1 == key2

    def test_documents_matching_with_defaults(self) -> None:
        """空值应有 fallback。"""
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_case_file_templates(
            case_type="civil", case_stage="", institutions="", version=1,
        )
        assert "civil" in key
        assert "1" in key


# =====================================================================
# CacheTimeout 超时计算
# =====================================================================


class TestCacheTimeout:
    """CacheTimeout.until_end_of_day 的时间计算。"""

    def test_until_end_of_day_returns_positive(self) -> None:
        """任何时间调用都应返回正数。"""
        from apps.core.infrastructure.cache import CacheTimeout
        now = datetime.datetime(2026, 6, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        result = CacheTimeout.until_end_of_day(now=now, buffer_seconds=3600)
        assert result > 3600  # 至少大于 buffer

    def test_until_end_of_day_includes_buffer(self) -> None:
        """buffer_seconds 应被加到结果中。"""
        from apps.core.infrastructure.cache import CacheTimeout
        now = datetime.datetime(2026, 6, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        r1 = CacheTimeout.until_end_of_day(now=now, buffer_seconds=0)
        r2 = CacheTimeout.until_end_of_day(now=now, buffer_seconds=3600)
        assert r2 == r1 + 3600

    def test_until_end_of_day_later_time_smaller_result(self) -> None:
        """更晚的时间应返回更小的结果。"""
        from apps.core.infrastructure.cache import CacheTimeout
        early = datetime.datetime(2026, 6, 7, 6, 0, 0, tzinfo=datetime.timezone.utc)
        late = datetime.datetime(2026, 6, 7, 18, 0, 0, tzinfo=datetime.timezone.utc)
        assert CacheTimeout.until_end_of_day(now=early) > CacheTimeout.until_end_of_day(now=late)

    def test_until_end_of_day_minimum_one(self) -> None:
        """返回值至少为 1。"""
        from apps.core.infrastructure.cache import CacheTimeout
        late = datetime.datetime(2026, 6, 7, 23, 59, 59, tzinfo=datetime.timezone.utc)
        result = CacheTimeout.until_end_of_day(now=late, buffer_seconds=0)
        assert result >= 1

    def test_short_medium_long_constants(self) -> None:
        """标准超时常量应存在。"""
        from apps.core.infrastructure.cache import CacheTimeout
        assert CacheTimeout.SHORT == 60
        assert CacheTimeout.MEDIUM == 300
        assert CacheTimeout.LONG == 3600
        assert CacheTimeout.DAY == 86400


# =====================================================================
# RateLimiter 限流器
# =====================================================================


class TestRateLimiter:
    """RateLimiter 的 IP 提取、缓存键生成、限流判定。"""

    def _make_request(self, *, remote_addr: str | None = None, xff: str | None = None) -> MagicMock:
        """构造假的 HttpRequest。"""
        request = MagicMock()
        request.META = {}
        if remote_addr:
            request.META["REMOTE_ADDR"] = remote_addr
        if xff:
            request.META["HTTP_X_FORWARDED_FOR"] = xff
        request.path = "/api/v1/test/"
        return request

    def test_get_client_ip_remote_addr_only(self) -> None:
        """只有 REMOTE_ADDR 时应返回该值。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter()
        request = self._make_request(remote_addr="10.0.0.1")
        assert rl.get_client_ip(request) == "10.0.0.1"

    def test_get_client_ip_unknown(self) -> None:
        """无任何 IP 信息时应返回 'unknown'。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter()
        request = self._make_request()
        assert rl.get_client_ip(request) == "unknown"

    def test_get_cache_key_deterministic(self) -> None:
        """相同请求应生成相同的缓存键。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter()
        request = self._make_request(remote_addr="1.2.3.4")
        key1 = rl.get_cache_key(request)
        key2 = rl.get_cache_key(request)
        assert key1 == key2
        assert rl.key_prefix in key1

    def test_get_cache_key_different_ips(self) -> None:
        """不同 IP 应生成不同的缓存键。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter()
        req1 = self._make_request(remote_addr="1.1.1.1")
        req2 = self._make_request(remote_addr="2.2.2.2")
        assert rl.get_cache_key(req1) != rl.get_cache_key(req2)

    def test_is_allowed_first_request(self) -> None:
        """首次请求应被允许。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter(requests=10, window=60)
        request = self._make_request(remote_addr="10.0.0.1")

        with patch("apps.core.infrastructure.throttling.cache") as mock_cache:
            mock_cache.add.return_value = True  # 首次初始化成功
            allowed, info = rl.is_allowed(request)

        assert allowed is True
        assert info["limit"] == 10
        assert info["remaining"] == 9

    def test_is_allowed_at_limit(self) -> None:
        """达到限制时应被拒绝。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter(requests=5, window=60)
        request = self._make_request(remote_addr="10.0.0.1")

        with patch("apps.core.infrastructure.throttling.cache") as mock_cache:
            mock_cache.add.return_value = False  # key 已存在
            mock_cache.incr.return_value = 6  # 超过限制
            allowed, info = rl.is_allowed(request)

        assert allowed is False
        assert info["remaining"] == 0

    def test_init_defaults(self) -> None:
        """默认参数应正确设置。"""
        from apps.core.infrastructure.throttling import RateLimiter
        rl = RateLimiter()
        assert rl.requests == 100
        assert rl.window == 60
        assert rl.key_prefix == "ratelimit"


# =====================================================================
# EvidenceService 链式计算
# =====================================================================


class TestEvidenceServiceChainCalculation:
    """EvidenceService 的 calculate_start_order 和 calculate_start_page。"""

    def _make_list(self, pk: int, item_count: int, total_pages: int, previous=None):
        """构造 mock EvidenceList。"""
        el = MagicMock()
        el.pk = pk
        el.total_pages = total_pages
        el.previous_list_id = previous.pk if previous else None
        el.previous_list = previous
        items_mgr = MagicMock()
        items_mgr.count.return_value = item_count
        el.items = items_mgr
        return el

    def test_start_order_no_previous(self) -> None:
        """无前序清单时应返回 1。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        el = self._make_list(pk=1, item_count=5, total_pages=10)
        assert svc.calculate_start_order(el) == 1

    def test_start_order_single_predecessor(self) -> None:
        """单个前序（3 项）时应返回 4。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        pred = self._make_list(pk=1, item_count=3, total_pages=10)
        curr = self._make_list(pk=2, item_count=2, total_pages=5, previous=pred)
        assert svc.calculate_start_order(curr) == 4

    def test_start_order_chain_of_three(self) -> None:
        """链 A(2) -> B(3) -> C，C 的 start_order 应为 6。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        a = self._make_list(pk=1, item_count=2, total_pages=10)
        b = self._make_list(pk=2, item_count=3, total_pages=20, previous=a)
        c = self._make_list(pk=3, item_count=1, total_pages=5, previous=b)
        assert svc.calculate_start_order(c) == 6

    def test_start_order_cycle_returns_one(self) -> None:
        """环形引用应返回 1（安全降级）。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        a = self._make_list(pk=1, item_count=2, total_pages=10)
        b = self._make_list(pk=2, item_count=3, total_pages=20, previous=a)
        a.previous_list = b  # 形成环
        a.previous_list_id = b.pk
        assert svc.calculate_start_order(b) == 1

    def test_start_page_no_previous(self) -> None:
        """无前序清单时 start_page 应返回 1。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        el = self._make_list(pk=1, item_count=0, total_pages=10)
        assert svc.calculate_start_page(el) == 1

    def test_start_page_chain(self) -> None:
        """链 A(10p) -> B(20p) -> C，C 的 start_page 应为 31。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        a = self._make_list(pk=1, item_count=0, total_pages=10)
        b = self._make_list(pk=2, item_count=0, total_pages=20, previous=a)
        c = self._make_list(pk=3, item_count=0, total_pages=5, previous=b)
        assert svc.calculate_start_page(c) == 31

    def test_start_page_cycle_returns_one(self) -> None:
        """环形引用时 start_page 应返回 1。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        a = self._make_list(pk=1, item_count=0, total_pages=10)
        b = self._make_list(pk=2, item_count=0, total_pages=20, previous=a)
        a.previous_list = b
        a.previous_list_id = b.pk
        assert svc.calculate_start_page(b) == 1


# =====================================================================
# CaseSearchQueryBuilder 搜索查询
# =====================================================================


class TestCaseSearchQueryBuilder:
    """CaseSearchQueryBuilder 的搜索逻辑。"""

    @pytest.mark.django_db
    def test_empty_query_returns_none(self) -> None:
        """空查询应返回空 QuerySet。"""
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        from apps.cases.models import Case
        qs = builder.build_case_search_queryset(Case.objects.all(), "")
        assert qs.count() == 0

    @pytest.mark.django_db
    def test_whitespace_query_returns_none(self) -> None:
        """纯空格查询应返回空 QuerySet。"""
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        from apps.cases.models import Case
        qs = builder.build_case_search_queryset(Case.objects.all(), "   ")
        assert qs.count() == 0

    @pytest.mark.django_db
    def test_search_by_case_name(self) -> None:
        """按案件名称搜索应返回匹配结果。"""
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        from apps.cases.models import Case

        case = CaseFactory(name="张三诉李四案")
        CaseFactory(name="王五诉赵六案")

        qs = builder.build_case_search_queryset(Case.objects.all(), "张三")
        assert case.pk in list(qs.values_list("pk", flat=True))

    @pytest.mark.django_db
    def test_search_with_status_filter(self) -> None:
        """带 status 过滤时应只返回匹配状态的案件。"""
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        from apps.cases.models import Case

        active = CaseFactory(name="活跃案件", status="active")
        CaseFactory(name="关闭案件", status="closed")

        qs = builder.build_case_search_queryset(Case.objects.all(), "案件", status="active")
        pks = list(qs.values_list("pk", flat=True))
        assert active.pk in pks
        assert len(qs) == 1

    @pytest.mark.django_db
    def test_search_respects_limit(self) -> None:
        """limit 参数应限制返回数量。"""
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        from apps.cases.models import Case

        for i in range(10):
            CaseFactory(name=f"测试案件{i}")

        qs = builder.build_case_search_queryset(Case.objects.all(), "测试", limit=3)
        assert qs.count() <= 3


# =====================================================================
# invalidate_user_access_context 缓存失效
# =====================================================================


class TestInvalidateUserAccessContext:
    """invalidate_user_access_context 应正确清除缓存键。"""

    def test_invalidate_both(self) -> None:
        """默认应清除 org_access 和 access_grants。"""
        from apps.core.infrastructure.cache import invalidate_user_access_context
        with patch("django.core.cache.cache") as mock_cache:
            invalidate_user_access_context(42)
            mock_cache.delete_many.assert_called_once()
            keys = mock_cache.delete_many.call_args[0][0]
            assert any("org_access" in k for k in keys)
            assert any("access_grants" in k for k in keys)

    def test_invalidate_org_access_only(self) -> None:
        """org_access=True, case_grants=False 应只清除 org_access。"""
        from apps.core.infrastructure.cache import invalidate_user_access_context
        with patch("django.core.cache.cache") as mock_cache:
            invalidate_user_access_context(42, org_access=True, case_grants=False)
            keys = mock_cache.delete_many.call_args[0][0]
            assert any("org_access" in k for k in keys)
            assert not any("access_grants" in k for k in keys)

    def test_invalidate_neither(self) -> None:
        """两个标志都为 False 时不应调用 delete_many。"""
        from apps.core.infrastructure.cache import invalidate_user_access_context
        with patch("django.core.cache.cache") as mock_cache:
            invalidate_user_access_context(42, org_access=False, case_grants=False)
            mock_cache.delete_many.assert_not_called()
