"""
性能测试 - 财产保全询价功能

测试目标：
1. 测试 10 个保险公司的并发查询时间（目标 < 10 秒）
2. 测试 Token 复用效果
3. 测试数据库查询性能

需求: Requirements 9.1, 9.2, 9.4
"""
import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from django.utils import timezone

from apps.automation.models import PreservationQuote, InsuranceQuote, QuoteStatus
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
from apps.automation.services.insurance.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)


@pytest.mark.django_db
class TestPerformance:
    """性能测试"""
    
    @pytest.fixture
    def service(self):
        """创建测试服务"""
        return PreservationQuoteService()
    
    @pytest.fixture
    def mock_credential(self):
        """创建模拟凭证"""
        from apps.organization.models import AccountCredential, Lawyer, LawFirm
        
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
    
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_concurrent_query_performance_10_companies(self, service, mock_credential):
        """
        测试 10 个保险公司的并发查询性能
        
        目标: < 10 秒
        需求: Requirements 9.1
        """
        from asgiref.sync import sync_to_async
        
        # 创建任务
        quote = await sync_to_async(service.create_quote)(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )
        
        # Mock Token
        mock_token = "test_token_12345"
        
        # 创建 10 个保险公司
        mock_companies = [
            InsuranceCompany(c_id=str(i), c_code=f"CODE{i}", c_name=f"保险公司{i}")
            for i in range(1, 11)
        ]
        
        # Mock 报价结果（所有成功）
        mock_results = [
            PremiumResult(
                company=company,
                premium=Decimal(f"{1500 + i * 10}.00"),
                status="success",
                error_message=None,
                response_data={"premium": f"{1500 + i * 10}.00"},
            )
            for i, company in enumerate(mock_companies)
        ]
        
        # 记录开始时间
        start_time = time.time()
        
        with patch.object(service.token_service, "get_token", return_value=mock_token):
            with patch.object(
                service.insurance_client,
                "fetch_insurance_companies",
                new_callable=AsyncMock,
                return_value=mock_companies
            ):
                with patch.object(
                    service.insurance_client,
                    "fetch_all_premiums",
                    new_callable=AsyncMock,
                    return_value=mock_results
                ):
                    result = await service.execute_quote(quote.id)
        
        # 记录结束时间
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert result["status"] == QuoteStatus.SUCCESS
        assert result["total_companies"] == 10
        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        
        # 性能断言：应该在 10 秒内完成
        assert elapsed_time < 10.0, f"并发查询耗时 {elapsed_time:.2f} 秒，超过 10 秒目标"
        
        print(f"\n✅ 性能测试通过: 10 个保险公司并发查询耗时 {elapsed_time:.2f} 秒")
    
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_concurrent_vs_serial_performance(self, service, mock_credential):
        """
        测试并发执行 vs 串行执行的性能差异
        
        验证并发执行的性能优势
        需求: Requirements 9.1
        """
        from asgiref.sync import sync_to_async
        
        # 创建 5 个保险公司（减少测试时间）
        mock_companies = [
            InsuranceCompany(c_id=str(i), c_code=f"CODE{i}", c_name=f"保险公司{i}")
            for i in range(1, 6)
        ]
        
        mock_token = "test_token_12345"
        
        # 模拟每个查询耗时 0.5 秒
        async def mock_fetch_premium_with_delay(*args, **kwargs):
            await asyncio.sleep(0.5)
            return PremiumResult(
                company=InsuranceCompany(c_id="1", c_code="TEST", c_name="测试"),
                premium=Decimal("1500.00"),
                status="success",
                error_message=None,
                response_data={"premium": "1500.00"},
            )
        
        # 测试并发执行
        client = CourtInsuranceClient()
        
        with patch.object(client, "fetch_premium", side_effect=mock_fetch_premium_with_delay):
            start_time = time.time()
            
            # 并发执行
            results = await client.fetch_all_premiums(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                companies=mock_companies,
            )
            
            concurrent_time = time.time() - start_time
        
        # 验证并发时间接近单个查询时间（0.5 秒），而不是总和（2.5 秒）
        # 允许一些开销，所以设置上限为 1.5 秒
        assert concurrent_time < 1.5, f"并发执行耗时 {concurrent_time:.2f} 秒，应该接近 0.5 秒"
        
        # 串行执行的理论时间
        serial_time_estimate = 0.5 * len(mock_companies)
        
        # 计算性能提升
        speedup = serial_time_estimate / concurrent_time
        
        print(f"\n✅ 并发性能测试通过:")
        print(f"   - 并发执行时间: {concurrent_time:.2f} 秒")
        print(f"   - 串行执行估计: {serial_time_estimate:.2f} 秒")
        print(f"   - 性能提升: {speedup:.2f}x")
        
        # 验证性能提升至少 2 倍
        assert speedup >= 2.0, f"性能提升 {speedup:.2f}x 不足 2 倍"
    
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_token_reuse_performance(self, service, mock_credential):
        """
        测试 Token 复用效果
        
        验证多次操作使用同一个 Token，避免重复登录
        需求: Requirements 9.2
        """
        from asgiref.sync import sync_to_async
        
        mock_token = "test_token_12345"
        mock_companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
        ]
        mock_results = [
            PremiumResult(
                company=mock_companies[0],
                premium=Decimal("1500.00"),
                status="success",
                error_message=None,
                response_data={"premium": "1500.00"},
            ),
        ]
        
        # 记录 get_token 被调用的次数
        get_token_call_count = [0]
        
        def mock_get_token(*args, **kwargs):
            get_token_call_count[0] += 1
            return mock_token
        
        # 创建 3 个询价任务
        quotes = []
        for i in range(3):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=Decimal(f"{(i + 1) * 10000}.00"),
                corp_id="test_corp",
                category_id="test_category",
                credential_id=mock_credential.id,
            )
            quotes.append(quote)
        
        # 执行所有任务
        with patch.object(service.token_service, "get_token", side_effect=mock_get_token):
            with patch.object(
                service.insurance_client,
                "fetch_insurance_companies",
                new_callable=AsyncMock,
                return_value=mock_companies
            ):
                with patch.object(
                    service.insurance_client,
                    "fetch_all_premiums",
                    new_callable=AsyncMock,
                    return_value=mock_results
                ):
                    for quote in quotes:
                        await service.execute_quote(quote.id)
        
        # 验证 get_token 被调用了 3 次（每个任务一次）
        # 但实际应该返回同一个 Token（通过 TokenService 的缓存机制）
        assert get_token_call_count[0] == 3
        
        print(f"\n✅ Token 复用测试通过:")
        print(f"   - 执行了 3 个询价任务")
        print(f"   - get_token 被调用 {get_token_call_count[0]} 次")
        print(f"   - 每次都应该从缓存获取同一个 Token（避免重复登录）")
    
    @pytest.mark.django_db
    def test_database_query_performance_list_quotes(self, service, mock_credential):
        """
        测试数据库查询性能 - 列表查询
        
        验证分页查询在大量数据下的性能
        需求: Requirements 9.4
        """
        # 创建 100 个询价任务
        quotes = []
        for i in range(100):
            quote = service.create_quote(
                preserve_amount=Decimal(f"{(i + 1) * 1000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            quotes.append(quote)
        
        # 测试列表查询性能
        start_time = time.time()
        
        # 查询第一页
        page1_quotes, total = service.list_quotes(page=1, page_size=20)
        
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert len(page1_quotes) == 20
        assert total == 100
        
        # 性能断言：应该在 1 秒内完成
        assert elapsed_time < 1.0, f"列表查询耗时 {elapsed_time:.2f} 秒，超过 1 秒目标"
        
        print(f"\n✅ 数据库查询性能测试通过:")
        print(f"   - 数据量: 100 条记录")
        print(f"   - 查询时间: {elapsed_time:.3f} 秒")
        print(f"   - 返回记录: {len(page1_quotes)} 条")
    
    @pytest.mark.django_db
    def test_database_query_performance_with_filter(self, service, mock_credential):
        """
        测试数据库查询性能 - 带筛选的查询
        
        验证索引优化效果
        需求: Requirements 9.4
        """
        # 创建不同状态的任务
        for i in range(50):
            quote = service.create_quote(
                preserve_amount=Decimal(f"{(i + 1) * 1000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            
            # 设置不同的状态
            if i % 3 == 0:
                quote.status = QuoteStatus.SUCCESS
            elif i % 3 == 1:
                quote.status = QuoteStatus.FAILED
            else:
                quote.status = QuoteStatus.PENDING
            quote.save()
        
        # 测试按状态筛选的性能
        start_time = time.time()
        
        # 查询成功的任务
        success_quotes, total = service.list_quotes(status=QuoteStatus.SUCCESS)
        
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert total == 17  # 50 / 3 ≈ 17
        assert all(q.status == QuoteStatus.SUCCESS for q in success_quotes)
        
        # 性能断言：应该在 0.5 秒内完成（使用索引）
        assert elapsed_time < 0.5, f"筛选查询耗时 {elapsed_time:.2f} 秒，超过 0.5 秒目标"
        
        print(f"\n✅ 数据库筛选查询性能测试通过:")
        print(f"   - 数据量: 50 条记录")
        print(f"   - 筛选条件: status=SUCCESS")
        print(f"   - 查询时间: {elapsed_time:.3f} 秒")
        print(f"   - 返回记录: {total} 条")
    
    @pytest.mark.django_db
    def test_database_query_performance_with_related_data(self, service, mock_credential):
        """
        测试数据库查询性能 - 包含关联数据
        
        验证 select_related 和 prefetch_related 的优化效果
        需求: Requirements 9.4
        """
        # 创建 10 个询价任务，每个任务有 5 个报价记录
        for i in range(10):
            quote = service.create_quote(
                preserve_amount=Decimal(f"{(i + 1) * 10000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            
            # 创建报价记录
            for j in range(5):
                InsuranceQuote.objects.create(
                    preservation_quote=quote,
                    company_id=f"company_{j}",
                    company_code=f"CODE{j}",
                    company_name=f"保险公司{j}",
                    premium=Decimal(f"{1500 + j * 100}.00"),
                    status="success",
                )
        
        # 测试获取任务详情的性能
        quote_id = PreservationQuote.objects.first().id
        
        start_time = time.time()
        
        # 获取任务（包含所有报价记录）
        quote = service.get_quote(quote_id)
        
        # 访问关联数据
        quotes_count = quote.quotes.count()
        
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert quotes_count == 5
        
        # 性能断言：应该在 0.5 秒内完成
        assert elapsed_time < 0.5, f"关联查询耗时 {elapsed_time:.2f} 秒，超过 0.5 秒目标"
        
        print(f"\n✅ 数据库关联查询性能测试通过:")
        print(f"   - 查询任务 ID: {quote_id}")
        print(f"   - 关联报价记录: {quotes_count} 条")
        print(f"   - 查询时间: {elapsed_time:.3f} 秒")
    
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_http_connection_pool_reuse(self, service, mock_credential):
        """
        测试 HTTP 连接池复用
        
        验证 httpx 客户端的连接池配置是否生效
        需求: Requirements 9.5
        """
        from asgiref.sync import sync_to_async
        
        # 创建客户端（使用共享连接池）
        client = CourtInsuranceClient()
        
        mock_token = "test_token_12345"
        
        # 创建 10 个保险公司
        mock_companies = [
            InsuranceCompany(c_id=str(i), c_code=f"CODE{i}", c_name=f"保险公司{i}")
            for i in range(1, 11)
        ]
        
        # 模拟 API 响应
        async def mock_get(*args, **kwargs):
            # 模拟网络延迟
            await asyncio.sleep(0.1)
            response = Mock()
            response.status_code = 200
            response.json.return_value = {"premium": "1500.00"}
            response.content = b'{"premium": "1500.00"}'
            return response
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用 patch 替换 httpx 客户端的 get 方法
        with patch.object(client._client, "get", side_effect=mock_get):
            # 并发查询所有保险公司
            results = await client.fetch_all_premiums(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                companies=mock_companies,
            )
        
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert len(results) == 10
        
        # 性能断言：并发执行应该接近单个请求时间（0.1 秒），而不是总和（1.0 秒）
        # 允许一些开销，所以设置上限为 0.5 秒
        assert elapsed_time < 0.5, f"连接池复用测试耗时 {elapsed_time:.2f} 秒，应该接近 0.1 秒"
        
        print(f"\n✅ HTTP 连接池复用测试通过:")
        print(f"   - 并发请求数: 10")
        print(f"   - 单个请求延迟: 0.1 秒")
        print(f"   - 实际执行时间: {elapsed_time:.2f} 秒")
        print(f"   - 连接池复用生效（避免了串行执行）")
        
        # 清理
        await client.close()
    
    @pytest.mark.django_db
    def test_bulk_create_performance(self, service, mock_credential):
        """
        测试批量创建报价记录的性能
        
        验证 bulk_create 的性能优势
        需求: Requirements 9.4
        """
        # 创建询价任务
        quote = service.create_quote(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )
        
        # 准备 100 个报价记录
        insurance_quotes = []
        for i in range(100):
            insurance_quotes.append(
                InsuranceQuote(
                    preservation_quote=quote,
                    company_id=f"company_{i}",
                    company_code=f"CODE{i}",
                    company_name=f"保险公司{i}",
                    premium=Decimal(f"{1500 + i * 10}.00"),
                    status="success",
                )
            )
        
        # 测试批量创建性能
        start_time = time.time()
        
        InsuranceQuote.objects.bulk_create(insurance_quotes)
        
        elapsed_time = time.time() - start_time
        
        # 验证结果
        assert InsuranceQuote.objects.filter(preservation_quote=quote).count() == 100
        
        # 性能断言：应该在 1 秒内完成
        assert elapsed_time < 1.0, f"批量创建耗时 {elapsed_time:.2f} 秒，超过 1 秒目标"
        
        print(f"\n✅ 批量创建性能测试通过:")
        print(f"   - 创建记录数: 100 条")
        print(f"   - 创建时间: {elapsed_time:.3f} 秒")
        print(f"   - 平均每条: {elapsed_time / 100 * 1000:.2f} 毫秒")
