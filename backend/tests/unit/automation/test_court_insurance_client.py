"""
CourtInsuranceClient 单元测试

测试 CourtInsuranceClient 的核心功能：
- 依赖注入
- 获取保险公司列表
- 查询保险公司报价
- 异常处理
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from apps.automation.services.insurance.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)
from apps.automation.services.scraper.core.token_service import TokenService
from apps.core.exceptions import APIError, NetworkError, TokenError


@pytest.mark.django_db
class TestCourtInsuranceClientInit:
    """测试 CourtInsuranceClient 初始化和依赖注入"""

    def test_init_without_token_service(self):
        """测试不提供 TokenService 时自动创建"""
        client = CourtInsuranceClient()

        assert client.token_service is not None
        assert isinstance(client.token_service, TokenService)

    def test_init_with_token_service(self):
        """测试注入自定义 TokenService"""
        mock_token_service = Mock(spec=TokenService)
        client = CourtInsuranceClient(token_service=mock_token_service)

        assert client.token_service is mock_token_service

    def test_init_creates_httpx_client(self):
        """测试初始化时创建 httpx 客户端"""
        client = CourtInsuranceClient()

        assert client._client is not None
        assert isinstance(client._client, httpx.AsyncClient)


@pytest.mark.django_db
@pytest.mark.anyio
class TestFetchInsuranceCompanies:
    """测试获取保险公司列表"""

    async def test_fetch_insurance_companies_success(self):
        """测试成功获取保险公司列表"""
        # 准备测试数据
        mock_response_data = {
            "data": [
                {"cId": "1", "cCode": "PICC", "cName": "中国人保"},
                {"cId": "2", "cCode": "CPIC", "cName": "中国太保"},
            ]
        }

        # 创建 Mock 响应（使用 Mock 而不是 AsyncMock）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.url = "https://test.com"
        mock_response.content = b"test"
        mock_response.text = "test"

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.get = AsyncMock(return_value=mock_response)

        # 执行测试
        companies = await client.fetch_insurance_companies(
            bearer_token="test_token",
            c_pid="test_pid",
            fy_id="test_fy_id",
            timeout=30.0,
        )

        # 验证结果
        assert len(companies) == 2
        assert companies[0].c_id == "1"
        assert companies[0].c_code == "PICC"
        assert companies[0].c_name == "中国人保"
        assert companies[1].c_id == "2"
        assert companies[1].c_code == "CPIC"
        assert companies[1].c_name == "中国太保"

        # 验证 API 调用
        client._client.get.assert_called_once()
        call_args = client._client.get.call_args
        assert call_args.kwargs["params"]["cPid"] == "test_pid"
        assert call_args.kwargs["params"]["fyId"] == "test_fy_id"
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test_token"

    async def test_fetch_insurance_companies_timeout(self):
        """测试获取保险公司列表超时"""
        # 创建客户端并 Mock httpx 客户端抛出超时异常
        client = CourtInsuranceClient()
        client._client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        # 执行测试并验证抛出 NetworkError
        with pytest.raises(NetworkError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token="test_token",
                c_pid="test_pid",
                fy_id="test_fy_id",
                timeout=30.0,
                max_retries=1,  # 只重试 1 次以加快测试
            )

        assert "超时" in exc_info.value.message
        assert exc_info.value.code == "INSURANCE_LIST_TIMEOUT"

    async def test_fetch_insurance_companies_http_error(self):
        """测试获取保险公司列表 HTTP 错误"""
        # 创建 Mock 响应（HTTP 500）
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.url = "https://test.com"
        mock_response.request = Mock()

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.get = AsyncMock(return_value=mock_response)

        # 执行测试并验证抛出 APIError
        with pytest.raises(APIError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token="test_token",
                c_pid="test_pid",
                fy_id="test_fy_id",
                timeout=30.0,
                max_retries=1,
            )

        assert "HTTP 500" in exc_info.value.message
        assert exc_info.value.code == "INSURANCE_LIST_HTTP_ERROR"

    async def test_fetch_insurance_companies_network_error(self):
        """测试获取保险公司列表网络错误"""
        # 创建客户端并 Mock httpx 客户端抛出连接错误
        client = CourtInsuranceClient()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))

        # 执行测试并验证抛出 NetworkError
        with pytest.raises(NetworkError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token="test_token",
                c_pid="test_pid",
                fy_id="test_fy_id",
                timeout=30.0,
                max_retries=1,
            )

        assert "网络错误" in exc_info.value.message
        assert exc_info.value.code == "INSURANCE_LIST_NETWORK_ERROR"

    async def test_fetch_insurance_companies_retry_on_network_error(self):
        """测试网络错误时自动重试"""
        # 创建客户端
        client = CourtInsuranceClient()

        # Mock httpx 客户端：前 2 次失败，第 3 次成功
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"data": []})
        mock_response.url = "https://test.com"
        mock_response.content = b"test"
        mock_response.text = "test"

        client._client.get = AsyncMock(
            side_effect=[
                httpx.ConnectError("Connection failed"),
                httpx.ConnectError("Connection failed"),
                mock_response,
            ]
        )

        # 执行测试
        companies = await client.fetch_insurance_companies(
            bearer_token="test_token",
            c_pid="test_pid",
            fy_id="test_fy_id",
            timeout=30.0,
            max_retries=3,
        )

        # 验证结果
        assert companies == []
        assert client._client.get.call_count == 3

    async def test_fetch_insurance_companies_empty_list(self):
        """测试返回空列表"""
        # 创建 Mock 响应（空列表）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"data": []})
        mock_response.url = "https://test.com"
        mock_response.content = b"test"
        mock_response.text = "test"

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.get = AsyncMock(return_value=mock_response)

        # 执行测试
        companies = await client.fetch_insurance_companies(
            bearer_token="test_token",
            c_pid="test_pid",
            fy_id="test_fy_id",
            timeout=30.0,
        )

        # 验证结果
        assert companies == []


@pytest.mark.django_db
@pytest.mark.anyio
class TestFetchPremium:
    """测试查询保险公司报价"""

    async def test_fetch_premium_success(self):
        """测试成功查询报价"""
        # 准备测试数据
        mock_response_data = {
            "data": {
                "minPremium": "100.00",
                "minAmount": "100.00",
                "minRate": "0.01",
                "maxRate": "0.02",
                "maxAmount": "200.00",
                "maxApplyAmount": "10000.00",
            }
        }

        # 创建 Mock 响应（使用 Mock 而不是 AsyncMock）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.url = "https://test.com"
        mock_response.text = "test"
        mock_response.headers = {}
        mock_response.content = b"test"

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.post = AsyncMock(return_value=mock_response)

        # 执行测试
        result = await client.fetch_premium(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            institution="PICC",
            corp_id="test_corp_id",
            timeout=30.0,
        )

        # 验证结果
        assert result.status == "success"
        assert result.premium == Decimal("100.00")
        assert result.company.c_code == "PICC"
        assert result.error_message is not None  # 成功时也记录完整信息
        assert result.response_data == mock_response_data

        # 验证 API 调用
        client._client.post.assert_called_once()
        call_args = client._client.post.call_args
        assert call_args.kwargs["params"]["institution"] == "PICC"
        assert call_args.kwargs["json"]["preserveAmount"] == "10000"

    async def test_fetch_premium_timeout(self):
        """测试查询报价超时（返回失败结果而非抛出异常）"""
        # 创建客户端并 Mock httpx 客户端抛出超时异常
        client = CourtInsuranceClient()
        client._client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        # 执行测试
        result = await client.fetch_premium(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            institution="PICC",
            corp_id="test_corp_id",
            timeout=30.0,
        )

        # 验证结果（返回失败结果）
        assert result.status == "failed"
        assert result.premium is None
        assert "超时" in result.error_message

    async def test_fetch_premium_http_error(self):
        """测试查询报价 HTTP 错误（返回失败结果）"""
        # 创建 Mock 响应（HTTP 500）
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.url = "https://test.com"
        mock_response.headers = {}
        mock_response.content = b"test"

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.post = AsyncMock(return_value=mock_response)

        # 执行测试
        result = await client.fetch_premium(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            institution="PICC",
            corp_id="test_corp_id",
            timeout=30.0,
        )

        # 验证结果（返回失败结果）
        assert result.status == "failed"
        assert result.premium is None
        assert "HTTP 500" in result.error_message

    async def test_fetch_premium_no_premium_data(self):
        """测试响应中没有报价数据"""
        # 创建 Mock 响应（没有 minPremium 字段）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"data": {}})
        mock_response.url = "https://test.com"
        mock_response.text = "test"
        mock_response.headers = {}
        mock_response.content = b"test"

        # 创建客户端并 Mock httpx 客户端
        client = CourtInsuranceClient()
        client._client.post = AsyncMock(return_value=mock_response)

        # 执行测试
        result = await client.fetch_premium(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            institution="PICC",
            corp_id="test_corp_id",
            timeout=30.0,
        )

        # 验证结果（返回失败结果）
        assert result.status == "failed"
        assert result.premium is None
        assert "未找到费率数据" in result.error_message


@pytest.mark.django_db
@pytest.mark.anyio
class TestFetchAllPremiums:
    """测试并发查询所有保险公司报价"""

    async def test_fetch_all_premiums_success(self):
        """测试成功并发查询所有报价"""
        # 准备测试数据
        companies = [
            InsuranceCompany(c_id="1", c_code="PICC", c_name="中国人保"),
            InsuranceCompany(c_id="2", c_code="CPIC", c_name="中国太保"),
        ]

        # Mock fetch_premium 方法
        async def mock_fetch_premium(bearer_token, preserve_amount, institution, corp_id, timeout):
            return PremiumResult(
                company=InsuranceCompany(c_id="", c_code=institution, c_name=""),
                premium=Decimal("100.00"),
                status="success",
                error_message=None,
                response_data={"data": {"minPremium": "100.00"}},
            )

        # 创建客户端并 Mock fetch_premium
        client = CourtInsuranceClient()
        client.fetch_premium = AsyncMock(side_effect=mock_fetch_premium)

        # 执行测试
        results = await client.fetch_all_premiums(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            corp_id="test_corp_id",
            companies=companies,
            timeout=30.0,
        )

        # 验证结果
        assert len(results) == 2
        assert all(r.status == "success" for r in results)
        assert all(r.premium == Decimal("100.00") for r in results)

        # 验证公司信息已补充
        assert results[0].company.c_name == "中国人保"
        assert results[1].company.c_name == "中国太保"

    async def test_fetch_all_premiums_empty_list(self):
        """测试空保险公司列表"""
        client = CourtInsuranceClient()

        results = await client.fetch_all_premiums(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            corp_id="test_corp_id",
            companies=[],
            timeout=30.0,
        )

        assert results == []

    async def test_fetch_all_premiums_partial_failure(self):
        """测试部分查询失败"""
        # 准备测试数据
        companies = [
            InsuranceCompany(c_id="1", c_code="PICC", c_name="中国人保"),
            InsuranceCompany(c_id="2", c_code="CPIC", c_name="中国太保"),
        ]

        # Mock fetch_premium 方法（第一个成功，第二个失败）
        async def mock_fetch_premium(bearer_token, preserve_amount, institution, corp_id, timeout):
            if institution == "PICC":
                return PremiumResult(
                    company=InsuranceCompany(c_id="", c_code=institution, c_name=""),
                    premium=Decimal("100.00"),
                    status="success",
                    error_message=None,
                    response_data={"data": {"minPremium": "100.00"}},
                )
            else:
                return PremiumResult(
                    company=InsuranceCompany(c_id="", c_code=institution, c_name=""),
                    premium=None,
                    status="failed",
                    error_message="查询失败",
                    response_data=None,
                )

        # 创建客户端并 Mock fetch_premium
        client = CourtInsuranceClient()
        client.fetch_premium = AsyncMock(side_effect=mock_fetch_premium)

        # 执行测试
        results = await client.fetch_all_premiums(
            bearer_token="test_token",
            preserve_amount=Decimal("10000.00"),
            corp_id="test_corp_id",
            companies=companies,
            timeout=30.0,
        )

        # 验证结果
        assert len(results) == 2
        assert results[0].status == "success"
        assert results[1].status == "failed"


@pytest.mark.django_db
@pytest.mark.anyio
class TestClientLifecycle:
    """测试客户端生命周期管理"""

    async def test_close_client(self):
        """测试关闭客户端"""
        client = CourtInsuranceClient()

        # Mock aclose 方法
        client._client.aclose = AsyncMock()

        # 执行关闭
        await client.close()

        # 验证 aclose 被调用
        client._client.aclose.assert_called_once()

    async def test_context_manager(self):
        """测试异步上下文管理器"""
        async with CourtInsuranceClient() as client:
            assert client is not None
            assert isinstance(client, CourtInsuranceClient)

            # Mock aclose 方法
            client._client.aclose = AsyncMock()

        # 验证退出时自动关闭
        client._client.aclose.assert_called_once()
