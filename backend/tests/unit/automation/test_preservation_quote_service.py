"""
测试 PreservationQuoteService

验证财产保全询价服务的基本功能
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.utils import timezone

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus
from apps.automation.services.insurance.court_insurance_client import InsuranceCompany, PremiumResult
from apps.automation.services.insurance.exceptions import TokenError, ValidationError
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
from apps.core.exceptions import NotFoundError


@pytest.mark.django_db
class TestPreservationQuoteService:
    """测试 PreservationQuoteService"""

    @pytest.fixture
    def mock_token_service(self):
        """创建 Mock TokenService"""
        return Mock()

    @pytest.fixture
    def mock_insurance_client(self):
        """创建 Mock CourtInsuranceClient"""
        return Mock()

    @pytest.fixture
    def mock_auto_token_service(self):
        """创建 Mock AutoTokenAcquisitionService"""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_token_service, mock_auto_token_service, mock_insurance_client):
        """创建测试服务（注入 Mock 依赖）"""
        return PreservationQuoteService(
            token_service=mock_token_service,
            auto_token_service=mock_auto_token_service,
            insurance_client=mock_insurance_client,
        )

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

    def test_create_quote_success(self, service, mock_credential):
        """测试成功创建询价任务"""
        quote = service.create_quote(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )

        assert quote.id is not None
        assert quote.preserve_amount == Decimal("100000.00")
        assert quote.corp_id == "test_corp"
        assert quote.category_id == "test_category"
        assert quote.credential_id == mock_credential.id
        assert quote.status == QuoteStatus.PENDING
        assert quote.total_companies == 0
        assert quote.success_count == 0
        assert quote.failed_count == 0

    def test_create_quote_invalid_amount(self, service, mock_credential):
        """测试保全金额为负数时抛出验证错误"""
        with pytest.raises(ValidationError) as exc_info:
            service.create_quote(
                preserve_amount=Decimal("-1000.00"),
                corp_id="test_corp",
                category_id="test_category",
                credential_id=mock_credential.id,
            )

        assert "保全金额必须为正数" in str(exc_info.value.errors)

    def test_create_quote_empty_corp_id(self, service, mock_credential):
        """测试法院 ID 为空时抛出验证错误"""
        with pytest.raises(ValidationError) as exc_info:
            service.create_quote(
                preserve_amount=Decimal("100000.00"),
                corp_id="",
                category_id="test_category",
                credential_id=mock_credential.id,
            )

        assert "法院 ID 不能为空" in str(exc_info.value.errors)

    def test_create_quote_empty_category_id(self, service, mock_credential):
        """测试分类 ID 为空时抛出验证错误"""
        with pytest.raises(ValidationError) as exc_info:
            service.create_quote(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="",
                credential_id=mock_credential.id,
            )

        assert "分类 ID 不能为空" in str(exc_info.value.errors)

    def test_get_quote_success(self, service, mock_credential):
        """测试成功获取询价任务"""
        # 创建任务
        created_quote = service.create_quote(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )

        # 获取任务
        quote = service.get_quote(created_quote.id)

        assert quote.id == created_quote.id
        assert quote.preserve_amount == Decimal("100000.00")

    def test_get_quote_not_found(self, service):
        """测试获取不存在的任务时抛出错误"""
        with pytest.raises(NotFoundError):
            service.get_quote(99999)

    def test_list_quotes_empty(self, service):
        """测试列表查询为空"""
        quotes, total = service.list_quotes()

        assert len(quotes) == 0
        assert total == 0

    def test_list_quotes_with_data(self, service, mock_credential):
        """测试列表查询有数据"""
        # 创建多个任务
        for i in range(5):
            service.create_quote(
                preserve_amount=Decimal(f"{(i + 1) * 10000}.00"),
                corp_id=f"corp_{i}",
                category_id=f"category_{i}",
                credential_id=mock_credential.id,
            )

        # 查询第一页
        quotes, total = service.list_quotes(page=1, page_size=3)

        assert len(quotes) == 3
        assert total == 5

        # 查询第二页
        quotes, total = service.list_quotes(page=2, page_size=3)

        assert len(quotes) == 2
        assert total == 5

    def test_list_quotes_filter_by_status(self, service, mock_credential):
        """测试按状态筛选"""
        # 创建不同状态的任务
        quote1 = service.create_quote(
            preserve_amount=Decimal("100000.00"),
            corp_id="corp_1",
            category_id="category_1",
            credential_id=mock_credential.id,
        )

        quote2 = service.create_quote(
            preserve_amount=Decimal("200000.00"),
            corp_id="corp_2",
            category_id="category_2",
            credential_id=mock_credential.id,
        )

        # 更新状态
        quote1.status = QuoteStatus.SUCCESS
        quote1.save()

        quote2.status = QuoteStatus.FAILED
        quote2.save()

        # 筛选成功的任务
        quotes, total = service.list_quotes(status=QuoteStatus.SUCCESS)

        assert len(quotes) == 1
        assert total == 1
        assert quotes[0].id == quote1.id

        # 筛选失败的任务
        quotes, total = service.list_quotes(status=QuoteStatus.FAILED)

        assert len(quotes) == 1
        assert total == 1
        assert quotes[0].id == quote2.id

    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_execute_quote_token_not_found(self, mock_token_service, mock_insurance_client, mock_credential):
        """测试 Token 不存在时抛出错误"""
        from asgiref.sync import sync_to_async

        # 创建服务实例
        mock_auto_token_service = AsyncMock()
        service = PreservationQuoteService(
            token_service=mock_token_service,
            auto_token_service=mock_auto_token_service,
            insurance_client=mock_insurance_client,
        )

        quote = await sync_to_async(service.create_quote)(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )

        # Mock TokenService.get_token 返回 None（模拟 Token 不存在）
        mock_token_service.get_token.return_value = None

        # 不设置 Token，直接执行
        with pytest.raises(TokenError) as exc_info:
            await service.execute_quote(quote.id)

        assert "Token 不存在或已过期" in str(exc_info.value.message)
        assert "/admin/automation/testcourt/" in str(exc_info.value.message)

    @pytest.mark.anyio
    async def test_execute_quote_not_found(self, service):
        """测试执行不存在的任务时抛出错误"""
        with pytest.raises(NotFoundError):
            await service.execute_quote(99999)

    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_execute_quote_success(self, mock_token_service, mock_insurance_client, mock_credential):
        """测试成功执行询价任务（使用 Mock）"""
        from asgiref.sync import sync_to_async

        # 创建服务实例
        mock_auto_token_service = AsyncMock()
        service = PreservationQuoteService(
            token_service=mock_token_service,
            auto_token_service=mock_auto_token_service,
            insurance_client=mock_insurance_client,
        )

        # 创建任务
        quote = await sync_to_async(service.create_quote)(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )

        # Mock Token Service
        mock_token = "test_token_12345"
        mock_token_service.get_token.return_value = mock_token

        # Mock 保险公司列表
        mock_companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
        ]

        # Mock 报价结果
        mock_results = [
            PremiumResult(
                company=mock_companies[0],
                premium=Decimal("1500.00"),
                status="success",
                error_message=None,
                response_data={"data": {"premium": "1500.00"}},
            ),
            PremiumResult(
                company=mock_companies[1],
                premium=Decimal("1600.00"),
                status="success",
                error_message=None,
                response_data={"data": {"premium": "1600.00"}},
            ),
        ]

        # 配置 Mock 行为
        mock_insurance_client.fetch_insurance_companies = AsyncMock(return_value=mock_companies)
        mock_insurance_client.fetch_all_premiums = AsyncMock(return_value=mock_results)

        result = await service.execute_quote(quote.id)

        # 验证返回结果
        assert result["quote_id"] == quote.id
        assert result["status"] == QuoteStatus.SUCCESS
        assert result["total_companies"] == 2
        assert result["success_count"] == 2
        assert result["failed_count"] == 0

        # 验证数据库记录
        await sync_to_async(quote.refresh_from_db)()
        assert quote.status == QuoteStatus.SUCCESS
        assert quote.total_companies == 2
        assert quote.success_count == 2
        assert quote.failed_count == 0
        assert quote.started_at is not None
        assert quote.finished_at is not None

        # 验证报价记录
        insurance_quotes_count = await sync_to_async(
            lambda: InsuranceQuote.objects.filter(preservation_quote=quote).count()
        )()
        assert insurance_quotes_count == 2

        quote_a = await sync_to_async(
            lambda: InsuranceQuote.objects.get(preservation_quote=quote, company_code="ABC")
        )()
        assert quote_a.company_name == "保险公司A"
        assert quote_a.premium == Decimal("1500.00")
        assert quote_a.status == QuoteItemStatus.SUCCESS

        quote_b = await sync_to_async(
            lambda: InsuranceQuote.objects.get(preservation_quote=quote, company_code="DEF")
        )()
        assert quote_b.company_name == "保险公司B"
        assert quote_b.premium == Decimal("1600.00")
        assert quote_b.status == QuoteItemStatus.SUCCESS

    @pytest.mark.anyio
    @pytest.mark.django_db(transaction=True)
    async def test_execute_quote_partial_success(self, mock_token_service, mock_insurance_client, mock_credential):
        """测试部分成功的询价任务（使用 Mock）"""
        from asgiref.sync import sync_to_async

        # 创建服务实例
        mock_auto_token_service = AsyncMock()
        service = PreservationQuoteService(
            token_service=mock_token_service,
            auto_token_service=mock_auto_token_service,
            insurance_client=mock_insurance_client,
        )

        quote = await sync_to_async(service.create_quote)(
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            category_id="test_category",
            credential_id=mock_credential.id,
        )

        mock_token = "test_token_12345"
        mock_token_service.get_token.return_value = mock_token

        mock_companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
        ]

        # 一个成功，一个失败
        mock_results = [
            PremiumResult(
                company=mock_companies[0],
                premium=Decimal("1500.00"),
                status="success",
                error_message=None,
                response_data={"data": {"premium": "1500.00"}},
            ),
            PremiumResult(
                company=mock_companies[1],
                premium=None,
                status="failed",
                error_message="HTTP 500: Internal Server Error",
                response_data=None,
            ),
        ]

        # 配置 Mock 行为
        mock_insurance_client.fetch_insurance_companies = AsyncMock(return_value=mock_companies)
        mock_insurance_client.fetch_all_premiums = AsyncMock(return_value=mock_results)

        result = await service.execute_quote(quote.id)

        # 验证返回结果
        assert result["status"] == QuoteStatus.PARTIAL_SUCCESS
        assert result["success_count"] == 1
        assert result["failed_count"] == 1

        # 验证数据库记录
        await sync_to_async(quote.refresh_from_db)()
        assert quote.status == QuoteStatus.PARTIAL_SUCCESS
        assert quote.success_count == 1
        assert quote.failed_count == 1

        # 验证报价记录
        insurance_quotes_count = await sync_to_async(
            lambda: InsuranceQuote.objects.filter(preservation_quote=quote).count()
        )()
        assert insurance_quotes_count == 2

        failed_quote = await sync_to_async(
            lambda: InsuranceQuote.objects.get(preservation_quote=quote, company_code="DEF")
        )()
        assert failed_quote.status == QuoteItemStatus.FAILED
        assert failed_quote.premium is None
        assert "HTTP 500" in failed_quote.error_message
