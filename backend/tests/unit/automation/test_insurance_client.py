"""
测试 CourtInsuranceClient

验证保险询价 API 客户端的基本功能
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from apps.automation.services.insurance.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)


class TestCourtInsuranceClient:
    """测试 CourtInsuranceClient"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return CourtInsuranceClient()

    @pytest.fixture
    def mock_token(self):
        """模拟 Token"""
        return "test_bearer_token_12345"

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_success(self, client, mock_token):
        """测试成功获取保险公司列表"""
        # 模拟 API 响应
        mock_response_data = {
            "data": [
                {"cId": "1", "cCode": "ABC", "cName": "保险公司A"},
                {"cId": "2", "cCode": "DEF", "cName": "保险公司B"},
                {"cId": "3", "cCode": "GHI", "cName": "保险公司C"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_async_client:
            # 配置 mock
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            # 执行测试
            companies = await client.fetch_insurance_companies(
                bearer_token=mock_token,
                c_pid="test_pid",
                fy_id="test_fy_id",
            )

            # 验证结果
            assert len(companies) == 3
            assert companies[0].c_id == "1"
            assert companies[0].c_code == "ABC"
            assert companies[0].c_name == "保险公司A"
            assert companies[1].c_id == "2"
            assert companies[2].c_id == "3"

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_empty_list(self, client, mock_token):
        """测试保险公司列表为空"""
        mock_response_data = {"data": []}

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            companies = await client.fetch_insurance_companies(
                bearer_token=mock_token,
                c_pid="test_pid",
                fy_id="test_fy_id",
            )

            assert len(companies) == 0

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_incomplete_data(self, client, mock_token):
        """测试保险公司信息不完整时跳过"""
        mock_response_data = {
            "data": [
                {"cId": "1", "cCode": "ABC", "cName": "保险公司A"},
                {"cId": "2", "cCode": "DEF"},  # 缺少 cName
                {"cId": "3", "cName": "保险公司C"},  # 缺少 cCode
                {"cCode": "GHI", "cName": "保险公司D"},  # 缺少 cId
            ]
        }

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            companies = await client.fetch_insurance_companies(
                bearer_token=mock_token,
                c_pid="test_pid",
                fy_id="test_fy_id",
            )

            # 只有第一个完整的记录被保留
            assert len(companies) == 1
            assert companies[0].c_id == "1"

    @pytest.mark.anyio
    async def test_fetch_premium_success(self, client, mock_token):
        """测试成功查询单个保险公司报价"""
        mock_response_data = {"premium": "1500.50", "data": {"premium": "1500.50"}}

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.fetch_premium(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                institution="ABC",
                corp_id="test_corp",
            )

            assert result.status == "success"
            assert result.premium == Decimal("1500.50")
            assert result.error_message is None
            assert result.response_data == mock_response_data

    @pytest.mark.anyio
    async def test_fetch_premium_no_premium_in_response(self, client, mock_token):
        """测试响应中没有报价金额"""
        mock_response_data = {"message": "success", "data": {}}

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.fetch_premium(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                institution="ABC",
                corp_id="test_corp",
            )

            assert result.status == "failed"
            assert result.premium is None
            assert "未找到报价金额" in result.error_message

    @pytest.mark.anyio
    async def test_fetch_premium_http_error(self, client, mock_token):
        """测试 HTTP 错误"""
        with patch("httpx.AsyncClient") as mock_async_client:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.fetch_premium(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                institution="ABC",
                corp_id="test_corp",
            )

            assert result.status == "failed"
            assert result.premium is None
            assert "HTTP 500" in result.error_message

    @pytest.mark.anyio
    async def test_fetch_premium_timeout(self, client, mock_token):
        """测试超时错误"""
        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException("Request timeout")
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            result = await client.fetch_premium(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                institution="ABC",
                corp_id="test_corp",
            )

            assert result.status == "failed"
            assert result.premium is None
            assert "超时" in result.error_message

    @pytest.mark.anyio
    async def test_fetch_all_premiums_success(self, client, mock_token):
        """测试并发查询所有保险公司报价"""
        companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
            InsuranceCompany(c_id="3", c_code="GHI", c_name="保险公司C"),
        ]

        # 模拟不同的响应
        mock_responses = [
            {"premium": "1500.00"},
            {"premium": "1600.00"},
            {"premium": "1400.00"},
        ]

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()

            # 为每次调用返回不同的响应
            call_count = [0]

            async def mock_get(*args, **kwargs):
                response = Mock()
                response.status_code = 200
                response.json.return_value = mock_responses[call_count[0]]
                call_count[0] += 1
                return response

            mock_client_instance.get = mock_get
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            results = await client.fetch_all_premiums(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                companies=companies,
            )

            assert len(results) == 3
            assert all(r.status == "success" for r in results)
            assert results[0].premium == Decimal("1500.00")
            assert results[1].premium == Decimal("1600.00")
            assert results[2].premium == Decimal("1400.00")

            # 验证公司信息被正确填充
            assert results[0].company.c_name == "保险公司A"
            assert results[1].company.c_name == "保险公司B"
            assert results[2].company.c_name == "保险公司C"

    @pytest.mark.anyio
    async def test_fetch_all_premiums_partial_failure(self, client, mock_token):
        """测试部分查询失败不影响其他查询"""
        companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
            InsuranceCompany(c_id="3", c_code="GHI", c_name="保险公司C"),
        ]

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client_instance = AsyncMock()

            call_count = [0]

            async def mock_get(*args, **kwargs):
                response = Mock()
                if call_count[0] == 1:  # 第二个请求失败
                    response.status_code = 500
                    response.text = "Error"
                else:
                    response.status_code = 200
                    response.json.return_value = {"premium": "1500.00"}
                call_count[0] += 1
                return response

            mock_client_instance.get = mock_get
            mock_async_client.return_value.__aenter__.return_value = mock_client_instance

            results = await client.fetch_all_premiums(
                bearer_token=mock_token,
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                companies=companies,
            )

            assert len(results) == 3
            assert results[0].status == "success"
            assert results[1].status == "failed"  # 第二个失败
            assert results[2].status == "success"

    @pytest.mark.anyio
    async def test_fetch_all_premiums_empty_list(self, client, mock_token):
        """测试空保险公司列表"""
        results = await client.fetch_all_premiums(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            corp_id="test_corp",
            companies=[],
        )

        assert len(results) == 0
