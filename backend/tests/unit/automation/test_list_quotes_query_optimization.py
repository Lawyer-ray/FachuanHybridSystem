"""
Property-Based Test: 关联查询避免 N+1 问题

Feature: backend-architecture-refactoring, Property 5: 关联查询避免 N+1 问题
Validates: Requirements 6.1, 6.2

测试 PreservationQuoteService.list_quotes 方法不会产生 N+1 查询问题
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.db import connection, reset_queries
from django.test.utils import override_settings
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService


@pytest.mark.django_db
class TestListQuotesQueryOptimization:
    """测试 list_quotes 方法的查询优化"""

    @pytest.fixture
    def mock_token_service(self):
        """创建 Mock TokenService"""
        return Mock()

    @pytest.fixture
    def mock_insurance_client(self):
        """创建 Mock CourtInsuranceClient"""
        return Mock()

    @pytest.fixture
    def service(self, mock_token_service, mock_insurance_client):
        """创建测试服务（注入 Mock 依赖）"""
        return PreservationQuoteService(token_service=mock_token_service, insurance_client=mock_insurance_client)

    @pytest.fixture
    def mock_credential(self):
        """创建模拟凭证"""
        from apps.organization.models import AccountCredential, LawFirm, Lawyer

        # 创建律所
        law_firm = LawFirm.objects.create(
            name="测试律所",
        )

        # 创建律师
        lawyer = Lawyer.objects.create(
            username="test_lawyer",
            real_name="测试律师",
            law_firm=law_firm,
        )

        # 创建凭证
        credential = AccountCredential.objects.create(
            lawyer=lawyer,
            account="test_account",
            password="test_password",
            site_name="court_zxfw",
            url="https://test.court.gov.cn",
        )
        return credential

    @given(num_quotes=st.integers(min_value=1, max_value=20), quotes_per_task=st.integers(min_value=0, max_value=5))
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @override_settings(DEBUG=True)
    def test_list_quotes_no_n_plus_1(self, service, mock_credential, num_quotes, quotes_per_task):
        """
        Property 5: 关联查询避免 N+1 问题

        验证 list_quotes 方法不会产生 N+1 查询：
        - 无论有多少个 PreservationQuote 记录
        - 无论每个 PreservationQuote 有多少个关联的 InsuranceQuote
        - 查询次数应该是固定的（不随记录数增加而线性增长）

        Feature: backend-architecture-refactoring, Property 5: 关联查询避免 N+1 问题
        Validates: Requirements 6.1, 6.2
        """
        # 清理之前的数据
        PreservationQuote.objects.all().delete()
        InsuranceQuote.objects.all().delete()

        # 创建测试数据
        for i in range(num_quotes):
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal(f"{(i + 1) * 10000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
                status=QuoteStatus.SUCCESS,
                total_companies=quotes_per_task,
                success_count=quotes_per_task,
                failed_count=0,
            )

            # 为每个询价任务创建关联的报价记录
            for j in range(quotes_per_task):
                InsuranceQuote.objects.create(
                    preservation_quote=quote,
                    company_id=f"company_{j}",
                    company_code=f"CODE_{j}",
                    company_name=f"保险公司{j}",
                    premium=Decimal(f"{(j + 1) * 100}.00"),
                    status=QuoteItemStatus.SUCCESS,
                )

        # 重置查询计数
        reset_queries()

        # 执行列表查询
        quotes, total = service.list_quotes(page=1, page_size=10)

        # 获取查询次数
        query_count = len(connection.queries)

        # 验证：查询次数应该是固定的，不随记录数增加
        # 预期查询：
        # 1. COUNT 查询（分页器获取总数）
        # 2. SELECT 查询（获取 PreservationQuote 列表）
        # 3. SELECT 查询（prefetch_related 预加载 InsuranceQuote）
        # 总共应该是 3 次查询，不管有多少条记录

        # 允许的最大查询次数（考虑到可能的额外查询，如事务相关）
        max_allowed_queries = 5

        assert query_count <= max_allowed_queries, (
            f"查询次数过多！预期 <= {max_allowed_queries}，实际 {query_count}。"
            f"这表明存在 N+1 查询问题。"
            f"\n记录数: {num_quotes}, 每个任务的报价数: {quotes_per_task}"
            f"\n查询详情:\n" + "\n".join([f"{i+1}. {q['sql'][:100]}..." for i, q in enumerate(connection.queries)])
        )

        # 验证返回的数据正确
        assert len(quotes) <= 10  # 分页大小
        assert total == num_quotes

        # 验证可以访问关联的 quotes 而不触发额外查询
        reset_queries()
        for quote in quotes:
            # 访问 prefetch_related 预加载的关系
            _ = list(quote.quotes.all())

        # 访问预加载的关系不应该产生额外查询
        additional_queries = len(connection.queries)
        assert additional_queries == 0, (
            f"访问预加载的关系产生了 {additional_queries} 次额外查询！" f"这表明 prefetch_related 没有正确工作。"
        )

    @override_settings(DEBUG=True)
    def test_list_quotes_query_count_baseline(self, service, mock_credential):
        """
        基准测试：验证查询次数的基准值

        这个测试使用固定的数据量，验证查询次数符合预期
        """
        # 清理数据
        PreservationQuote.objects.all().delete()
        InsuranceQuote.objects.all().delete()

        # 创建 5 个询价任务，每个有 3 个报价
        for i in range(5):
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal(f"{(i + 1) * 10000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
                status=QuoteStatus.SUCCESS,
                total_companies=3,
                success_count=3,
                failed_count=0,
            )

            for j in range(3):
                InsuranceQuote.objects.create(
                    preservation_quote=quote,
                    company_id=f"company_{j}",
                    company_code=f"CODE_{j}",
                    company_name=f"保险公司{j}",
                    premium=Decimal(f"{(j + 1) * 100}.00"),
                    status=QuoteItemStatus.SUCCESS,
                )

        # 重置查询计数
        reset_queries()

        # 执行查询
        quotes, total = service.list_quotes(page=1, page_size=10)

        # 获取查询次数
        query_count = len(connection.queries)

        # 打印查询详情（用于调试）
        print(f"\n查询次数: {query_count}")
        for i, query in enumerate(connection.queries):
            print(f"{i+1}. {query['sql'][:200]}")

        # 验证查询次数
        assert query_count <= 5, f"查询次数 {query_count} 超过预期"

        # 验证结果
        assert len(quotes) == 5
        assert total == 5

        # 验证可以访问关联数据而不触发额外查询
        reset_queries()
        for quote in quotes:
            quote_list = list(quote.quotes.all())
            assert len(quote_list) == 3

        additional_queries = len(connection.queries)
        assert additional_queries == 0, f"访问预加载的关系产生了 {additional_queries} 次额外查询"
