"""CourtInsuranceClient 全覆盖测试。"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.preservation_quote.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)


class TestInsuranceCompany:
    """InsuranceCompany 数据类测试。"""

    def test_creation(self) -> None:
        c = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        assert c.c_code == "PICC"


class TestPremiumResult:
    """PremiumResult 数据类测试。"""

    def test_creation(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        r = PremiumResult(company=company, premium=Decimal("100.00"), status="success", error_message=None, response_data={})
        assert r.status == "success"
        assert r.premium == Decimal("100.00")
        assert r.request_info is None


class TestCourtInsuranceClient:
    """CourtInsuranceClient 测试。"""

    def _make_client(self) -> CourtInsuranceClient:
        """Create client bypassing __init__."""
        client = CourtInsuranceClient.__new__(CourtInsuranceClient)
        client._token_service = MagicMock()
        client._client = MagicMock()
        return client

    # ─── _parse_insurance_companies ───

    def test_parse_from_dict_with_data(self) -> None:
        client = self._make_client()
        data = {"data": [{"cId": "1", "cCode": "PICC", "cName": "人保"}]}
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1
        assert companies[0].c_code == "PICC"

    def test_parse_from_list(self) -> None:
        client = self._make_client()
        data = [{"cId": "1", "cCode": "PICC", "cName": "人保"}]
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1

    def test_parse_unknown_format(self) -> None:
        client = self._make_client()
        companies = client._parse_insurance_companies("invalid")
        assert companies == []

    def test_parse_skip_incomplete(self) -> None:
        client = self._make_client()
        data = {"data": [{"cId": "1"}, {"cId": "2", "cCode": "C", "cName": "N"}]}
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1

    def test_parse_skip_non_dict(self) -> None:
        client = self._make_client()
        data = {"data": ["not_a_dict", {"cId": "1", "cCode": "C", "cName": "N"}]}
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1

    # ─── fetch_insurance_companies ───

    @pytest.mark.asyncio
    async def test_fetch_insurance_companies_success(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"cId": "1", "cCode": "P", "cName": "N"}]}
        client._client.get = AsyncMock(return_value=mock_response)

        with patch.object(type(client), "insurance_list_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)):
            companies = await client.fetch_insurance_companies("token", "pid", "fyid", max_retries=1)
            assert len(companies) == 1

    @pytest.mark.asyncio
    async def test_fetch_insurance_companies_retries_on_network_error(self) -> None:
        import httpx
        client = self._make_client()
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("conn fail"))

        with patch.object(type(client), "insurance_list_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception):
                await client.fetch_insurance_companies("token", "pid", "fyid", max_retries=2)

    @pytest.mark.asyncio
    async def test_fetch_insurance_companies_api_error_no_retry(self) -> None:
        import httpx
        from apps.core.exceptions import APIError

        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "bad request"
        mock_response.request = MagicMock()
        error = httpx.HTTPStatusError("400", request=mock_response.request, response=mock_response)
        client._client.get = AsyncMock(side_effect=error)

        with patch.object(type(client), "insurance_list_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)):
            with pytest.raises(APIError):
                await client.fetch_insurance_companies("token", "pid", "fyid", max_retries=3)

    @pytest.mark.asyncio
    async def test_fetch_insurance_companies_server_error_retried(self) -> None:
        import httpx
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "server error"
        mock_response.request = MagicMock()
        error = httpx.HTTPStatusError("500", request=mock_response.request, response=mock_response)
        client._client.get = AsyncMock(side_effect=error)

        with patch.object(type(client), "insurance_list_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception):
                await client.fetch_insurance_companies("token", "pid", "fyid", max_retries=1)

    @pytest.mark.asyncio
    async def test_fetch_insurance_companies_timeout(self) -> None:
        import httpx
        from apps.core.exceptions import NetworkError

        client = self._make_client()
        client._client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch.object(type(client), "insurance_list_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(NetworkError):
                await client.fetch_insurance_companies("token", "pid", "fyid", max_retries=1)

    # ─── fetch_premium ───

    @pytest.mark.asyncio
    async def test_fetch_premium_success(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"premium": "150.50"}}
        client._client.post = AsyncMock(return_value=mock_response)

        with patch.object(type(client), "premium_query_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch.object(client, "_build_premium_request", return_value=({}, {}, {}, {})), \
             patch.object(client, "_parse_premium_from_response", return_value=Decimal("150.50")):
            result = await client.fetch_premium("token", Decimal("10000"), "inst1", "corp1")
            assert result.status == "success"
            assert result.premium == Decimal("150.50")

    @pytest.mark.asyncio
    async def test_fetch_premium_no_premium_found(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        client._client.post = AsyncMock(return_value=mock_response)

        with patch.object(type(client), "premium_query_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch.object(client, "_build_premium_request", return_value=({}, {}, {}, {})), \
             patch.object(client, "_parse_premium_from_response", return_value=None):
            result = await client.fetch_premium("token", Decimal("10000"), "inst1", "corp1")
            assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_fetch_premium_http_error(self) -> None:
        import httpx
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "bad request"
        client._client.post = AsyncMock(side_effect=httpx.HTTPStatusError("400", request=MagicMock(), response=mock_response))

        with patch.object(type(client), "premium_query_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch.object(client, "_build_premium_request", return_value=({}, {}, {}, {})):
            result = await client.fetch_premium("token", Decimal("10000"), "inst1", "corp1")
            assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_fetch_premium_timeout(self) -> None:
        import httpx
        client = self._make_client()
        client._client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch.object(type(client), "premium_query_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch.object(client, "_build_premium_request", return_value=({}, {}, {}, {})):
            result = await client.fetch_premium("token", Decimal("10000"), "inst1", "corp1")
            assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_fetch_premium_unknown_exception(self) -> None:
        client = self._make_client()
        client._client.post = AsyncMock(side_effect=RuntimeError("unexpected"))

        with patch.object(type(client), "premium_query_url", new_callable=lambda: property(lambda self: "http://test")), \
             patch.object(type(client), "default_timeout", new_callable=lambda: property(lambda self: 10.0)), \
             patch.object(client, "_build_premium_request", return_value=({}, {}, {}, {})):
            result = await client.fetch_premium("token", Decimal("10000"), "inst1", "corp1")
            assert result.status == "failed"

    # ─── fetch_all_premiums ───

    @pytest.mark.asyncio
    async def test_fetch_all_premiums_empty(self) -> None:
        client = self._make_client()
        result = await client.fetch_all_premiums("token", Decimal("1000"), "corp", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_all_premiums_success(self) -> None:
        client = self._make_client()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        premium_result = PremiumResult(
            company=company, premium=Decimal("100"), status="success",
            error_message=None, response_data={},
        )

        async def mock_fetch_premium(**kwargs):
            return premium_result

        with patch.object(client, "fetch_premium", side_effect=mock_fetch_premium), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            results = await client.fetch_all_premiums("token", Decimal("1000"), "corp", [company])
            assert len(results) == 1
            assert results[0].status == "success"

    @pytest.mark.asyncio
    async def test_fetch_all_premiums_with_exception(self) -> None:
        client = self._make_client()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")

        async def mock_fetch_premium(**kwargs):
            raise RuntimeError("boom")

        with patch.object(client, "fetch_premium", side_effect=mock_fetch_premium), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            results = await client.fetch_all_premiums("token", Decimal("1000"), "corp", [company])
            assert len(results) == 1
            assert results[0].status == "failed"

    @pytest.mark.asyncio
    async def test_fetch_all_premiums_batches(self) -> None:
        client = self._make_client()
        companies = [
            InsuranceCompany(c_id=str(i), c_code=f"C{i}", c_name=f"N{i}")
            for i in range(5)
        ]

        async def mock_fetch_premium(**kwargs):
            return PremiumResult(
                company=InsuranceCompany(c_id="", c_code="C", c_name="N"),
                premium=Decimal("100"), status="success",
                error_message=None, response_data={},
            )

        with patch.object(client, "fetch_premium", side_effect=mock_fetch_premium), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            results = await client.fetch_all_premiums("token", Decimal("1000"), "corp", companies)
            assert len(results) == 5

    # ─── close ───

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = self._make_client()
        client._client.aclose = AsyncMock()
        await client.close()
        client._client.aclose.assert_called_once()

    # ─── async context manager ───

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        client = self._make_client()
        client._client.aclose = AsyncMock()
        async with client as c:
            assert c is client
        client._client.aclose.assert_called_once()
