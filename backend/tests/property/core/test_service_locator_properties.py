"""
ServiceLocator Property-Based Tests
测试服务定位器的缓存一致性

**Feature: service-layer-decoupling, Property 2: ServiceLocator 缓存一致性**
**Validates: Requirements 4.4**
"""
import pytest
from hypothesis import given, strategies as st, settings

from apps.core.interfaces import ServiceLocator


@pytest.mark.django_db
class TestServiceLocatorCacheConsistencyProperties:
    """
    ServiceLocator 缓存一致性属性测试

    **Feature: service-layer-decoupling, Property 2: ServiceLocator 缓存一致性**
    **Validates: Requirements 4.4**
    """

    def setup_method(self):
        """每个测试前清除 ServiceLocator 缓存"""
        ServiceLocator.clear()

    def teardown_method(self):
        """每个测试后清除 ServiceLocator 缓存"""
        ServiceLocator.clear()

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_case_service_cache_consistency(self, call_count: int):
        """
        Property 2: ServiceLocator 缓存一致性 - 案件服务

        *For any* 服务名称，连续两次调用 `ServiceLocator.get_xxx_service()`
        应返回同一个实例（引用相等）。

        **Validates: Requirements 4.4**
        """
        ServiceLocator.clear()
        first = ServiceLocator.get_case_service()

        for _ in range(call_count):
            current = ServiceLocator.get_case_service()
            assert current is first, "连续调用应返回同一实例"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_lawfirm_service_cache_consistency(self, call_count: int):
        """
        Property 2: ServiceLocator 缓存一致性 - 律所服务

        *For any* 服务名称，连续两次调用 `ServiceLocator.get_xxx_service()`
        应返回同一个实例（引用相等）。

        **Validates: Requirements 4.4**
        """
        ServiceLocator.clear()
        first = ServiceLocator.get_lawfirm_service()

        for _ in range(call_count):
            current = ServiceLocator.get_lawfirm_service()
            assert current is first, "连续调用应返回同一实例"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_client_service_cache_consistency(self, call_count: int):
        """
        Property 2: ServiceLocator 缓存一致性 - 客户服务

        *For any* 服务名称，连续两次调用 `ServiceLocator.get_xxx_service()`
        应返回同一个实例（引用相等）。

        **Validates: Requirements 4.4**
        """
        ServiceLocator.clear()
        first = ServiceLocator.get_client_service()

        for _ in range(call_count):
            current = ServiceLocator.get_client_service()
            assert current is first, "连续调用应返回同一实例"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_contract_service_cache_consistency(self, call_count: int):
        """
        Property 2: ServiceLocator 缓存一致性 - 合同服务

        *For any* 服务名称，连续两次调用 `ServiceLocator.get_xxx_service()`
        应返回同一个实例（引用相等）。

        **Validates: Requirements 4.4**
        """
        ServiceLocator.clear()
        first = ServiceLocator.get_contract_service()

        for _ in range(call_count):
            current = ServiceLocator.get_contract_service()
            assert current is first, "连续调用应返回同一实例"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_lawyer_service_cache_consistency(self, call_count: int):
        """
        Property 2: ServiceLocator 缓存一致性 - 律师服务

        *For any* 服务名称，连续两次调用 `ServiceLocator.get_xxx_service()`
        应返回同一个实例（引用相等）。

        **Validates: Requirements 4.4**
        """
        ServiceLocator.clear()
        first = ServiceLocator.get_lawyer_service()

        for _ in range(call_count):
            current = ServiceLocator.get_lawyer_service()
            assert current is first, "连续调用应返回同一实例"


@pytest.mark.django_db
class TestServiceLocatorClearProperties:
    """
    ServiceLocator clear 方法属性测试

    **Validates: Requirements 4.5**
    """

    def setup_method(self):
        """每个测试前清除 ServiceLocator 缓存"""
        ServiceLocator.clear()

    def teardown_method(self):
        """每个测试后清除 ServiceLocator 缓存"""
        ServiceLocator.clear()

    def test_clear_single_service(self):
        """
        测试清除单个服务

        清除单个服务后，该服务应被移除，其他服务不受影响。
        """
        # 获取多个服务
        case_service = ServiceLocator.get_case_service()
        client_service = ServiceLocator.get_client_service()

        # 清除案件服务
        ServiceLocator.clear("case_service")

        # 再次获取案件服务应该是新实例
        new_case_service = ServiceLocator.get_case_service()
        assert new_case_service is not case_service, "清除后应返回新实例"

        # 客户服务应该仍是同一实例
        same_client_service = ServiceLocator.get_client_service()
        assert same_client_service is client_service, "未清除的服务应保持不变"

    def test_clear_all_services(self):
        """
        测试清除所有服务

        清除所有服务后，所有服务都应被移除。
        """
        # 获取多个服务
        case_service = ServiceLocator.get_case_service()
        client_service = ServiceLocator.get_client_service()
        lawfirm_service = ServiceLocator.get_lawfirm_service()

        # 清除所有服务
        ServiceLocator.clear()

        # 再次获取应该都是新实例
        new_case_service = ServiceLocator.get_case_service()
        new_client_service = ServiceLocator.get_client_service()
        new_lawfirm_service = ServiceLocator.get_lawfirm_service()

        assert new_case_service is not case_service, "清除后案件服务应返回新实例"
        assert new_client_service is not client_service, "清除后客户服务应返回新实例"
        assert new_lawfirm_service is not lawfirm_service, "清除后律所服务应返回新实例"

    def test_clear_nonexistent_service(self):
        """
        测试清除不存在的服务

        清除不存在的服务不应抛出异常。
        """
        # 不应抛出异常
        ServiceLocator.clear("nonexistent_service")
