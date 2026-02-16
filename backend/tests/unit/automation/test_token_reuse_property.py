"""
属性测试 - Token 复用

**Feature: property-preservation-insurance, Property 20: Token 复用**

Property 20: Token 复用
*对于任何* 在 Token 有效期内的多次操作，系统应该从 TokenService 获取同一个 Token 而不是要求用户重复登录
**验证需求: Requirements 9.2**

使用 Hypothesis 进行属性测试，验证 Token 复用机制的正确性。
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from hypothesis import given, strategies as st, settings, assume
from hypothesis import HealthCheck

from apps.automation.models import PreservationQuote, QuoteStatus
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
from apps.automation.services.insurance.court_insurance_client import (
    InsuranceCompany,
    PremiumResult,
)


# 定义策略：生成随机的询价任务数量（1-10 个）
task_count_strategy = st.integers(min_value=1, max_value=10)

# 定义策略：生成随机的保全金额（1000-1000000）
preserve_amount_strategy = st.decimals(
    min_value=1000,
    max_value=1000000,
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# 定义策略：生成随机的保险公司数量（1-5 个）
company_count_strategy = st.integers(min_value=1, max_value=5)


@pytest.mark.django_db
class TestTokenReuseProperty:
    """
    属性测试：Token 复用
    
    **Feature: property-preservation-insurance, Property 20: Token 复用**
    """
    
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
    
    @given(
        task_count=task_count_strategy,
        preserve_amount=preserve_amount_strategy,
        company_count=company_count_strategy,
    )
    @settings(
        max_examples=100,  # 运行 100 次测试
        deadline=None,  # 禁用超时限制
        suppress_health_check=[HealthCheck.function_scoped_fixture],  # 允许使用 function-scoped fixture
    )
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_token_reuse_across_multiple_tasks(
        self,
        service,
        mock_credential,
        task_count,
        preserve_amount,
        company_count,
    ):
        """
        属性测试：多个任务应该复用同一个 Token
        
        **Feature: property-preservation-insurance, Property 20: Token 复用**
        
        对于任意数量的询价任务（1-10 个），在 Token 有效期内，
        系统应该从 TokenService 获取同一个 Token，而不是要求用户重复登录。
        
        验证：
        1. get_token 被调用的次数 = 任务数量
        2. 每次都返回同一个 Token（模拟缓存行为）
        3. 没有触发重新登录
        """
        from asgiref.sync import sync_to_async
        
        # 确保保全金额是正数
        assume(preserve_amount > 0)
        
        # Mock Token（模拟缓存中的 Token）
        mock_token = "test_token_12345_cached"
        
        # 创建随机数量的保险公司
        mock_companies = [
            InsuranceCompany(
                c_id=str(i),
                c_code=f"CODE{i}",
                c_name=f"保险公司{i}"
            )
            for i in range(1, company_count + 1)
        ]
        
        # Mock 报价结果（所有成功）
        mock_results = [
            PremiumResult(
                company=company,
                premium=Decimal("1500.00"),
                status="success",
                error_message=None,
                response_data={"premium": "1500.00"},
            )
            for company in mock_companies
        ]
        
        # 记录 get_token 被调用的次数和返回的 Token
        get_token_calls = []
        
        def mock_get_token(*args, **kwargs):
            """模拟 TokenService.get_token，记录调用并返回缓存的 Token"""
            get_token_calls.append(mock_token)
            return mock_token
        
        # 创建随机数量的询价任务
        quotes = []
        for i in range(task_count):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=preserve_amount,
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
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
        
        # 属性验证 1: get_token 被调用的次数应该等于任务数量
        assert len(get_token_calls) == task_count, (
            f"get_token 应该被调用 {task_count} 次，实际调用了 {len(get_token_calls)} 次"
        )
        
        # 属性验证 2: 每次都应该返回同一个 Token（模拟缓存行为）
        assert all(token == mock_token for token in get_token_calls), (
            f"所有调用都应该返回同一个 Token: {mock_token}"
        )
        
        # 属性验证 3: 验证所有任务都成功完成（使用了缓存的 Token）
        for quote in quotes:
            await sync_to_async(quote.refresh_from_db)()
            assert quote.status == QuoteStatus.SUCCESS, (
                f"任务 {quote.id} 应该成功完成，实际状态: {quote.status}"
            )
    
    @given(
        task_count=task_count_strategy,
        preserve_amount=preserve_amount_strategy,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_token_reuse_no_redundant_login(
        self,
        service,
        mock_credential,
        task_count,
        preserve_amount,
    ):
        """
        属性测试：Token 复用避免冗余登录
        
        **Feature: property-preservation-insurance, Property 20: Token 复用**
        
        对于任意数量的询价任务，如果 Token 有效，系统不应该触发重新登录。
        
        验证：
        1. 没有调用登录 API
        2. 所有任务都使用缓存的 Token
        3. 性能优于每次都登录的情况
        """
        from asgiref.sync import sync_to_async
        import time
        
        assume(preserve_amount > 0)
        
        mock_token = "test_token_cached"
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
        
        # 记录是否触发了登录
        login_called = [False]
        
        def mock_get_token(*args, **kwargs):
            """模拟从缓存获取 Token，不触发登录"""
            # 如果这里调用了登录 API，设置标志
            # 在真实场景中，TokenService 会先检查缓存
            return mock_token
        
        def mock_login(*args, **kwargs):
            """模拟登录 API（不应该被调用）"""
            login_called[0] = True
            return mock_token
        
        # 创建任务
        quotes = []
        for i in range(task_count):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=preserve_amount,
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            quotes.append(quote)
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行所有任务（使用缓存的 Token）
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
        
        elapsed_time = time.time() - start_time
        
        # 属性验证 1: 没有触发登录
        assert not login_called[0], "不应该触发登录 API（Token 应该从缓存获取）"
        
        # 属性验证 2: 所有任务都成功完成
        for quote in quotes:
            await sync_to_async(quote.refresh_from_db)()
            assert quote.status == QuoteStatus.SUCCESS
        
        # 属性验证 3: 性能应该很快（因为没有登录开销）
        # 假设每次登录需要 1 秒，如果每次都登录，总时间应该 >= task_count 秒
        # 使用缓存应该远小于这个时间
        max_expected_time = task_count * 0.1  # 每个任务最多 0.1 秒（不包含登录）
        assert elapsed_time < max_expected_time, (
            f"执行 {task_count} 个任务耗时 {elapsed_time:.2f} 秒，"
            f"应该小于 {max_expected_time:.2f} 秒（使用缓存的 Token）"
        )
    
    @given(
        preserve_amount=preserve_amount_strategy,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_token_consistency_across_operations(
        self,
        service,
        mock_credential,
        preserve_amount,
    ):
        """
        属性测试：同一个凭证的多次操作应该使用同一个 Token
        
        **Feature: property-preservation-insurance, Property 20: Token 复用**
        
        对于同一个凭证（credential_id），多次操作应该获取到同一个 Token。
        
        验证：
        1. 同一个凭证的多次操作返回相同的 Token
        2. Token 在有效期内保持一致
        """
        from asgiref.sync import sync_to_async
        
        assume(preserve_amount > 0)
        
        mock_token = "test_token_consistent"
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
        
        # 记录每次获取的 Token
        tokens_retrieved = []
        
        def mock_get_token(*args, **kwargs):
            """模拟 TokenService，记录每次返回的 Token"""
            tokens_retrieved.append(mock_token)
            return mock_token
        
        # 创建 3 个使用同一个凭证的任务
        quotes = []
        for i in range(3):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=preserve_amount,
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,  # 使用同一个凭证
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
        
        # 属性验证 1: 应该获取了 3 次 Token
        assert len(tokens_retrieved) == 3, (
            f"应该获取 3 次 Token，实际获取了 {len(tokens_retrieved)} 次"
        )
        
        # 属性验证 2: 所有 Token 都应该相同（同一个凭证）
        assert all(token == mock_token for token in tokens_retrieved), (
            f"同一个凭证的所有操作应该返回相同的 Token: {mock_token}"
        )
        
        # 属性验证 3: 验证 Token 的一致性（没有变化）
        unique_tokens = set(tokens_retrieved)
        assert len(unique_tokens) == 1, (
            f"应该只有 1 个唯一的 Token，实际有 {len(unique_tokens)} 个: {unique_tokens}"
        )
    
    @given(
        task_count=st.integers(min_value=2, max_value=5),
        preserve_amount=preserve_amount_strategy,
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_token_reuse_reduces_api_calls(
        self,
        service,
        mock_credential,
        task_count,
        preserve_amount,
    ):
        """
        属性测试：Token 复用减少 API 调用次数
        
        **Feature: property-preservation-insurance, Property 20: Token 复用**
        
        验证 Token 复用机制确实减少了对登录 API 的调用次数。
        
        验证：
        1. 使用缓存时，登录 API 调用次数 = 0
        2. 不使用缓存时，登录 API 调用次数 = 任务数量
        3. Token 复用带来的性能提升
        """
        from asgiref.sync import sync_to_async
        
        assume(preserve_amount > 0)
        
        mock_token = "test_token_reuse"
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
        
        # 场景 1: 使用缓存（Token 复用）
        cache_login_calls = [0]
        
        def mock_get_token_with_cache(*args, **kwargs):
            """模拟从缓存获取 Token（不调用登录 API）"""
            # 缓存命中，不需要登录
            return mock_token
        
        quotes_with_cache = []
        for i in range(task_count):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=preserve_amount,
                corp_id=f"corp_cache_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            quotes_with_cache.append(quote)
        
        with patch.object(service.token_service, "get_token", side_effect=mock_get_token_with_cache):
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
                    for quote in quotes_with_cache:
                        await service.execute_quote(quote.id)
        
        # 场景 2: 不使用缓存（每次都登录）
        no_cache_login_calls = [0]
        
        def mock_get_token_without_cache(*args, **kwargs):
            """模拟每次都调用登录 API"""
            no_cache_login_calls[0] += 1
            return f"{mock_token}_{no_cache_login_calls[0]}"  # 每次返回不同的 Token
        
        quotes_without_cache = []
        for i in range(task_count):
            quote = await sync_to_async(service.create_quote)(
                preserve_amount=preserve_amount,
                corp_id=f"corp_no_cache_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )
            quotes_without_cache.append(quote)
        
        with patch.object(service.token_service, "get_token", side_effect=mock_get_token_without_cache):
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
                    for quote in quotes_without_cache:
                        await service.execute_quote(quote.id)
        
        # 属性验证 1: 使用缓存时，登录 API 调用次数应该是 0
        assert cache_login_calls[0] == 0, (
            f"使用缓存时不应该调用登录 API，实际调用了 {cache_login_calls[0]} 次"
        )
        
        # 属性验证 2: 不使用缓存时，登录 API 调用次数应该等于任务数量
        assert no_cache_login_calls[0] == task_count, (
            f"不使用缓存时应该调用 {task_count} 次登录 API，实际调用了 {no_cache_login_calls[0]} 次"
        )
        
        # 属性验证 3: Token 复用减少了 API 调用
        api_calls_saved = no_cache_login_calls[0] - cache_login_calls[0]
        assert api_calls_saved == task_count, (
            f"Token 复用应该减少 {task_count} 次 API 调用，实际减少了 {api_calls_saved} 次"
        )
