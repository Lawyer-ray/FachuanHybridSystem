"""
CourtInsuranceClient Property-Based Tests

测试 CourtInsuranceClient 的通用属性：
- Property 2: 业务错误抛出自定义异常
"""
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, Mock
import httpx

from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.core.exceptions import NetworkError, APIError


@pytest.mark.django_db
@pytest.mark.anyio
class TestExceptionHandlingProperties:
    """测试异常处理的通用属性"""
    
    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_network_errors_raise_network_error(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str
    ):
        """
        **Feature: backend-architecture-refactoring, Property 2: 业务错误抛出自定义异常**
        **Validates: Requirements 5.1**
        
        Property: 当 API 调用发生网络错误时，应该抛出 NetworkError 异常
        
        For any bearer_token, c_pid, fy_id:
        - 当 httpx 抛出 TimeoutException 时，应该抛出 NetworkError
        - 当 httpx 抛出 ConnectError 时，应该抛出 NetworkError
        - 异常应该包含必要的错误信息（message, code, errors）
        """
        client = CourtInsuranceClient()
        
        # 测试 TimeoutException
        client._client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        
        with pytest.raises(NetworkError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token=bearer_token,
                c_pid=c_pid,
                fy_id=fy_id,
                timeout=30.0,
                max_retries=1,
            )
        
        # 验证异常包含必要信息
        assert exc_info.value.message is not None
        assert len(exc_info.value.message) > 0
        assert exc_info.value.code is not None
        assert isinstance(exc_info.value.errors, dict)
        assert "url" in exc_info.value.errors
        assert "timeout" in exc_info.value.errors
    
    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
        status_code=st.integers(min_value=400, max_value=599),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_http_errors_raise_api_error(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str,
        status_code: int
    ):
        """
        **Feature: backend-architecture-refactoring, Property 2: 业务错误抛出自定义异常**
        **Validates: Requirements 5.1**
        
        Property: 当 API 返回错误状态码时，应该抛出 APIError 异常
        
        For any bearer_token, c_pid, fy_id, and status_code in [400, 599]:
        - 当 HTTP 响应状态码不是 200 时，应该抛出 APIError
        - 异常应该包含必要的错误信息（message, code, errors）
        - errors 字段应该包含 status_code 和 response_text
        """
        client = CourtInsuranceClient()
        
        # 创建 Mock 响应
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.text = f"Error {status_code}"
        mock_response.url = "https://test.com"
        mock_response.content = b"test"
        mock_response.request = Mock()
        
        client._client.get = AsyncMock(return_value=mock_response)
        
        with pytest.raises(APIError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token=bearer_token,
                c_pid=c_pid,
                fy_id=fy_id,
                timeout=30.0,
                max_retries=1,
            )
        
        # 验证异常包含必要信息
        assert exc_info.value.message is not None
        assert len(exc_info.value.message) > 0
        assert exc_info.value.code is not None
        assert isinstance(exc_info.value.errors, dict)
        assert "url" in exc_info.value.errors
        assert "status_code" in exc_info.value.errors
        assert exc_info.value.errors["status_code"] == status_code
        assert "response_text" in exc_info.value.errors
    
    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_connect_errors_raise_network_error(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str
    ):
        """
        **Feature: backend-architecture-refactoring, Property 2: 业务错误抛出自定义异常**
        **Validates: Requirements 5.1**
        
        Property: 当发生连接错误时，应该抛出 NetworkError 异常
        
        For any bearer_token, c_pid, fy_id:
        - 当 httpx 抛出 ConnectError 时，应该抛出 NetworkError
        - 异常应该包含必要的错误信息
        """
        client = CourtInsuranceClient()
        
        # 测试 ConnectError
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        
        with pytest.raises(NetworkError) as exc_info:
            await client.fetch_insurance_companies(
                bearer_token=bearer_token,
                c_pid=c_pid,
                fy_id=fy_id,
                timeout=30.0,
                max_retries=1,
            )
        
        # 验证异常包含必要信息
        assert exc_info.value.message is not None
        assert len(exc_info.value.message) > 0
        assert exc_info.value.code is not None
        assert isinstance(exc_info.value.errors, dict)
        assert "url" in exc_info.value.errors
        assert "error_type" in exc_info.value.errors
        assert "original_error" in exc_info.value.errors
    
    @given(
        bearer_token=st.text(min_size=10, max_size=100),
        c_pid=st.text(min_size=1, max_size=50),
        fy_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50, deadline=None)
    async def test_property_exception_structure_consistency(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str
    ):
        """
        **Feature: backend-architecture-refactoring, Property 2: 业务错误抛出自定义异常**
        **Validates: Requirements 5.1, 5.4**
        
        Property: 所有自定义异常都应该有一致的结构
        
        For any bearer_token, c_pid, fy_id:
        - 所有异常都应该有 message 属性（字符串）
        - 所有异常都应该有 code 属性（字符串）
        - 所有异常都应该有 errors 属性（字典）
        - 所有异常都应该有 to_dict() 方法
        """
        client = CourtInsuranceClient()
        
        # 测试不同类型的错误
        error_scenarios = [
            (httpx.TimeoutException("Timeout"), NetworkError),
            (httpx.ConnectError("Connection failed"), NetworkError),
        ]
        
        for error, expected_exception_type in error_scenarios:
            client._client.get = AsyncMock(side_effect=error)
            
            try:
                await client.fetch_insurance_companies(
                    bearer_token=bearer_token,
                    c_pid=c_pid,
                    fy_id=fy_id,
                    timeout=30.0,
                    max_retries=1,
                )
                pytest.fail(f"Expected {expected_exception_type.__name__} to be raised")
            except expected_exception_type as exc:
                # 验证异常结构
                assert hasattr(exc, 'message')
                assert isinstance(exc.message, str)
                assert len(exc.message) > 0
                
                assert hasattr(exc, 'code')
                assert isinstance(exc.code, str)
                assert len(exc.code) > 0
                
                assert hasattr(exc, 'errors')
                assert isinstance(exc.errors, dict)
                
                assert hasattr(exc, 'to_dict')
                assert callable(exc.to_dict)
                
                # 验证 to_dict() 返回正确的结构
                error_dict = exc.to_dict()
                assert isinstance(error_dict, dict)
                assert 'error' in error_dict
                assert 'code' in error_dict
                assert 'errors' in error_dict
                assert error_dict['error'] == exc.message
                assert error_dict['code'] == exc.code
                assert error_dict['errors'] == exc.errors
