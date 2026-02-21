"""
CourtInsuranceClient Property-Based Tests
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.core.exceptions import APIError, NetworkError


@pytest.mark.django_db
class TestExceptionHandlingProperties:
    """测试异常处理的通用属性"""

    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=10, deadline=None)
    def test_property_network_errors_raise_network_error(
        self, bearer_token: str, c_pid: str, fy_id: str
    ) -> None:
        """Property: TimeoutException → NetworkError"""

        async def _run() -> None:
            client = CourtInsuranceClient()
            client._client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            with pytest.raises(NetworkError) as exc_info:
                await client.fetch_insurance_companies(
                    bearer_token=bearer_token, c_pid=c_pid, fy_id=fy_id,
                    timeout=30.0, max_retries=1,
                )
            assert exc_info.value.message
            assert exc_info.value.code
            assert isinstance(exc_info.value.errors, dict)
            assert "url" in exc_info.value.errors

        asyncio.run(_run())

    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
        status_code=st.integers(min_value=400, max_value=499),  # 只测 4xx → APIError
    )
    @settings(max_examples=10, deadline=None)
    def test_property_http_errors_raise_api_error(
        self, bearer_token: str, c_pid: str, fy_id: str, status_code: int
    ) -> None:
        """Property: HTTP 4xx → APIError（5xx → NetworkError，不在此测）"""

        async def _run() -> None:
            client = CourtInsuranceClient()
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = f"Error {status_code}"
            mock_response.url = "https://test.com"
            mock_response.content = b"test"
            mock_response.request = Mock()
            client._client.get = AsyncMock(return_value=mock_response)
            with pytest.raises(APIError) as exc_info:
                await client.fetch_insurance_companies(
                    bearer_token=bearer_token, c_pid=c_pid, fy_id=fy_id,
                    timeout=30.0, max_retries=1,
                )
            assert exc_info.value.message
            assert exc_info.value.code
            assert isinstance(exc_info.value.errors, dict)
            assert "status_code" in exc_info.value.errors
            assert exc_info.value.errors["status_code"] == status_code

        asyncio.run(_run())

    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=10, deadline=None)
    def test_property_connect_errors_raise_network_error(
        self, bearer_token: str, c_pid: str, fy_id: str
    ) -> None:
        """Property: ConnectError → NetworkError"""

        async def _run() -> None:
            client = CourtInsuranceClient()
            client._client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            with pytest.raises(NetworkError) as exc_info:
                await client.fetch_insurance_companies(
                    bearer_token=bearer_token, c_pid=c_pid, fy_id=fy_id,
                    timeout=30.0, max_retries=1,
                )
            assert exc_info.value.message
            assert exc_info.value.code
            assert isinstance(exc_info.value.errors, dict)
            assert "url" in exc_info.value.errors

        asyncio.run(_run())

    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=5, deadline=None)
    def test_property_exception_structure_consistency(
        self, bearer_token: str, c_pid: str, fy_id: str
    ) -> None:
        """Property: 所有自定义异常结构一致"""

        async def _run() -> None:
            client = CourtInsuranceClient()
            for error, expected_type in [
                (httpx.TimeoutException("Timeout"), NetworkError),
                (httpx.ConnectError("Connection failed"), NetworkError),
            ]:
                client._client.get = AsyncMock(side_effect=error)
                try:
                    await client.fetch_insurance_companies(
                        bearer_token=bearer_token, c_pid=c_pid, fy_id=fy_id,
                        timeout=30.0, max_retries=1,
                    )
                    pytest.fail(f"Expected {expected_type.__name__}")
                except expected_type as exc:
                    assert isinstance(exc.message, str) and exc.message
                    assert isinstance(exc.code, str) and exc.code
                    assert isinstance(exc.errors, dict)
                    error_dict = exc.to_dict()
                    assert error_dict["error"] == exc.message
                    assert error_dict["code"] == exc.code

        asyncio.run(_run())
