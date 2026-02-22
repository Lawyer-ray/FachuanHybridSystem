"""
测试 CourtInsuranceClient

验证保险询价 API 客户端的基本功能
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

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
    def client(self) -> CourtInsuranceClient:
        return CourtInsuranceClient()

    @pytest.fixture
    def mock_token(self) -> str:
        return "test_bearer_token_12345"

    def _mock_get(self, client: CourtInsuranceClient, data: dict, status: int = 200) -> None:
        mock_resp = Mock()
        mock_resp.status_code = status
        mock_resp.json.return_value = data
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        client._client = mock_http

    def _mock_post(
        self, client: CourtInsuranceClient, data: dict | None = None, status: int = 200, text: str = ""
    ) -> None:  # noqa: E501
        mock_resp = Mock()
        mock_resp.status_code = status
        mock_resp.text = text
        if data is not None:
            mock_resp.json.return_value = data
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        client._client = mock_http

    # ── fetch_insurance_companies ──────────────────────────────────────────

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_success(self, client: CourtInsuranceClient, mock_token: str) -> None:
        self._mock_get(
            client,
            {
                "data": [
                    {"cId": "1", "cCode": "ABC", "cName": "保险公司A"},
                    {"cId": "2", "cCode": "DEF", "cName": "保险公司B"},
                    {"cId": "3", "cCode": "GHI", "cName": "保险公司C"},
                ]
            },
        )

        companies = await client.fetch_insurance_companies(bearer_token=mock_token, c_pid="pid", fy_id="fid")

        assert len(companies) == 3
        assert companies[0].c_id == "1"
        assert companies[0].c_code == "ABC"
        assert companies[0].c_name == "保险公司A"
        assert companies[1].c_id == "2"
        assert companies[2].c_id == "3"

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_empty_list(self, client: CourtInsuranceClient, mock_token: str) -> None:
        self._mock_get(client, {"data": []})
        companies = await client.fetch_insurance_companies(bearer_token=mock_token, c_pid="pid", fy_id="fid")
        assert len(companies) == 0

    @pytest.mark.anyio
    async def test_fetch_insurance_companies_incomplete_data(
        self, client: CourtInsuranceClient, mock_token: str
    ) -> None:  # noqa: E501
        self._mock_get(
            client,
            {
                "data": [
                    {"cId": "1", "cCode": "ABC", "cName": "保险公司A"},
                    {"cId": "2", "cCode": "DEF"},  # 缺 cName
                    {"cId": "3", "cName": "保险公司C"},  # 缺 cCode
                    {"cCode": "GHI", "cName": "保险公司D"},  # 缺 cId
                ]
            },
        )
        companies = await client.fetch_insurance_companies(bearer_token=mock_token, c_pid="pid", fy_id="fid")
        assert len(companies) == 1
        assert companies[0].c_id == "1"

    # ── fetch_premium ──────────────────────────────────────────────────────

    @pytest.mark.anyio
    async def test_fetch_premium_success(self, client: CourtInsuranceClient, mock_token: str) -> None:
        resp_data = {"data": {"minPremium": "1500.50"}}
        self._mock_post(client, resp_data)

        result = await client.fetch_premium(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            institution="ABC",
            corp_id="corp",
        )

        assert result.status == "success"
        assert result.premium == Decimal("1500.50")
        assert result.response_data == resp_data

    @pytest.mark.anyio
    async def test_fetch_premium_no_premium_in_response(self, client: CourtInsuranceClient, mock_token: str) -> None:
        self._mock_post(client, {"data": {}})

        result = await client.fetch_premium(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            institution="ABC",
            corp_id="corp",
        )

        assert result.status == "failed"
        assert result.premium is None
        assert "未找到" in result.error_message  # type: ignore[operator]

    @pytest.mark.anyio
    async def test_fetch_premium_http_error(self, client: CourtInsuranceClient, mock_token: str) -> None:
        self._mock_post(client, status=500, text="Internal Server Error")

        result = await client.fetch_premium(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            institution="ABC",
            corp_id="corp",
        )

        assert result.status == "failed"
        assert result.premium is None
        assert "HTTP 500" in result.error_message  # type: ignore[operator]

    @pytest.mark.anyio
    async def test_fetch_premium_timeout(self, client: CourtInsuranceClient, mock_token: str) -> None:
        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.TimeoutException("timeout")
        client._client = mock_http

        result = await client.fetch_premium(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            institution="ABC",
            corp_id="corp",
        )

        assert result.status == "failed"
        assert result.premium is None
        assert "超时" in result.error_message  # type: ignore[operator]

    # ── fetch_all_premiums ─────────────────────────────────────────────────

    @pytest.mark.anyio
    async def test_fetch_all_premiums_success(self, client: CourtInsuranceClient, mock_token: str) -> None:
        companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
            InsuranceCompany(c_id="3", c_code="GHI", c_name="保险公司C"),
        ]
        premiums = ["1500.00", "1600.00", "1400.00"]
        call_count = [0]

        async def mock_post(*args: object, **kwargs: object) -> Mock:
            resp = Mock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"minPremium": premiums[call_count[0]]}}
            call_count[0] += 1
            return resp

        mock_http = AsyncMock()
        mock_http.post = mock_post
        client._client = mock_http

        results = await client.fetch_all_premiums(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            corp_id="corp",
            companies=companies,
        )

        assert len(results) == 3
        assert all(r.status == "success" for r in results)
        assert results[0].premium == Decimal("1500.00")
        assert results[1].premium == Decimal("1600.00")
        assert results[2].premium == Decimal("1400.00")
        assert results[0].company.c_name == "保险公司A"
        assert results[1].company.c_name == "保险公司B"
        assert results[2].company.c_name == "保险公司C"

    @pytest.mark.anyio
    async def test_fetch_all_premiums_partial_failure(self, client: CourtInsuranceClient, mock_token: str) -> None:
        companies = [
            InsuranceCompany(c_id="1", c_code="ABC", c_name="保险公司A"),
            InsuranceCompany(c_id="2", c_code="DEF", c_name="保险公司B"),
            InsuranceCompany(c_id="3", c_code="GHI", c_name="保险公司C"),
        ]
        call_count = [0]

        async def mock_post(*args: object, **kwargs: object) -> Mock:
            resp = Mock()
            if call_count[0] == 1:
                resp.status_code = 500
                resp.text = "Error"
            else:
                resp.status_code = 200
                resp.json.return_value = {"data": {"minPremium": "1500.00"}}
            call_count[0] += 1
            return resp

        mock_http = AsyncMock()
        mock_http.post = mock_post
        client._client = mock_http

        results = await client.fetch_all_premiums(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            corp_id="corp",
            companies=companies,
        )

        assert len(results) == 3
        assert results[0].status == "success"
        assert results[1].status == "failed"
        assert results[2].status == "success"

    @pytest.mark.anyio
    async def test_fetch_all_premiums_empty_list(self, client: CourtInsuranceClient, mock_token: str) -> None:
        results = await client.fetch_all_premiums(
            bearer_token=mock_token,
            preserve_amount=Decimal("100000.00"),
            corp_id="corp",
            companies=[],
        )
        assert len(results) == 0
