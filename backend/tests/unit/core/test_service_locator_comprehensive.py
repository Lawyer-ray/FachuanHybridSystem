"""
测试 ServiceLocator 服务定位器
"""

import pytest

from apps.core.service_locator_base import BaseServiceLocator


class MockService:
    """模拟服务类"""

    def __init__(self, name: str):
        self.name = name

    def get_name(self) -> str:
        return self.name


class TestBaseServiceLocator:
    """测试 BaseServiceLocator 基类"""

    def setup_method(self):
        """每个测试前清理服务"""
        BaseServiceLocator.clear()

    def teardown_method(self):
        """每个测试后清理服务"""
        BaseServiceLocator.clear()

    def test_register_and_get_service(self):
        """测试注册和获取服务"""
        service = MockService("test_service")
        BaseServiceLocator.register("test", service)

        retrieved = BaseServiceLocator.get("test")
        assert retrieved is service
        assert retrieved.get_name() == "test_service"

    def test_get_nonexistent_service_returns_none(self):
        """测试获取不存在的服务返回 None"""
        result = BaseServiceLocator.get("nonexistent")
        assert result is None

    def test_register_multiple_services(self):
        """测试注册多个服务"""
        service1 = MockService("service1")
        service2 = MockService("service2")
        service3 = MockService("service3")

        BaseServiceLocator.register("s1", service1)
        BaseServiceLocator.register("s2", service2)
        BaseServiceLocator.register("s3", service3)

        assert BaseServiceLocator.get("s1") is service1
        assert BaseServiceLocator.get("s2") is service2
        assert BaseServiceLocator.get("s3") is service3

    def test_register_overwrites_existing_service(self):
        """测试注册会覆盖已存在的服务"""
        service1 = MockService("first")
        service2 = MockService("second")

        BaseServiceLocator.register("test", service1)
        assert BaseServiceLocator.get("test").get_name() == "first"

        BaseServiceLocator.register("test", service2)
        assert BaseServiceLocator.get("test").get_name() == "second"

    def test_clear_specific_service(self):
        """测试清除特定服务"""
        service1 = MockService("service1")
        service2 = MockService("service2")

        BaseServiceLocator.register("s1", service1)
        BaseServiceLocator.register("s2", service2)

        BaseServiceLocator.clear("s1")

        assert BaseServiceLocator.get("s1") is None
        assert BaseServiceLocator.get("s2") is service2

    def test_clear_all_services(self):
        """测试清除所有服务"""
        service1 = MockService("service1")
        service2 = MockService("service2")

        BaseServiceLocator.register("s1", service1)
        BaseServiceLocator.register("s2", service2)

        BaseServiceLocator.clear()

        assert BaseServiceLocator.get("s1") is None
        assert BaseServiceLocator.get("s2") is None

    def test_clear_nonexistent_service_does_not_raise(self):
        """测试清除不存在的服务不会抛出异常"""
        BaseServiceLocator.clear("nonexistent")  # 不应该抛出异常

    def test_get_or_create_creates_new_service(self):
        """测试 get_or_create 创建新服务"""

        def factory():
            return MockService("created")

        result = BaseServiceLocator.get_or_create("test", factory)

        assert result.get_name() == "created"
        assert BaseServiceLocator.get("test") is result

    def test_get_or_create_returns_existing_service(self):
        """测试 get_or_create 返回已存在的服务"""
        existing = MockService("existing")
        BaseServiceLocator.register("test", existing)

        factory_called = False

        def factory():
            nonlocal factory_called
            factory_called = True
            return MockService("new")

        result = BaseServiceLocator.get_or_create("test", factory)

        assert result is existing
        assert not factory_called  # 工厂函数不应该被调用

    def test_scope_isolates_services(self):
        """测试 scope 隔离服务"""
        global_service = MockService("global")
        BaseServiceLocator.register("test", global_service)

        with BaseServiceLocator.scope():
            # 在 scope 内，全局服务不可见
            assert BaseServiceLocator.get("test") is None

            # 在 scope 内注册的服务
            scoped_service = MockService("scoped")
            BaseServiceLocator.register("test", scoped_service)
            assert BaseServiceLocator.get("test") is scoped_service

        # scope 外，全局服务仍然存在
        assert BaseServiceLocator.get("test") is global_service

    def test_nested_scopes(self):
        """测试嵌套 scope"""
        global_service = MockService("global")
        BaseServiceLocator.register("test", global_service)

        with BaseServiceLocator.scope():
            scope1_service = MockService("scope1")
            BaseServiceLocator.register("test", scope1_service)
            assert BaseServiceLocator.get("test") is scope1_service

            with BaseServiceLocator.scope():
                # 嵌套 scope 内看不到外层 scope 的服务
                assert BaseServiceLocator.get("test") is None

                scope2_service = MockService("scope2")
                BaseServiceLocator.register("test", scope2_service)
                assert BaseServiceLocator.get("test") is scope2_service

            # 回到第一层 scope
            assert BaseServiceLocator.get("test") is scope1_service

        # 回到全局
        assert BaseServiceLocator.get("test") is global_service

    def test_scope_exception_cleanup(self):
        """测试 scope 异常时的清理"""
        global_service = MockService("global")
        BaseServiceLocator.register("test", global_service)

        try:
            with BaseServiceLocator.scope():
                scoped_service = MockService("scoped")
                BaseServiceLocator.register("test", scoped_service)
                raise ValueError("Test exception")
        except ValueError:
            pass

        # 即使发生异常，scope 也应该被清理，全局服务应该恢复
        assert BaseServiceLocator.get("test") is global_service

    def test_register_different_types(self):
        """测试注册不同类型的对象"""
        # 注册类实例
        service = MockService("test")
        BaseServiceLocator.register("service", service)
        assert BaseServiceLocator.get("service") is service

        # 注册字符串
        BaseServiceLocator.register("string", "test_string")
        assert BaseServiceLocator.get("string") == "test_string"

        # 注册数字
        BaseServiceLocator.register("number", 42)
        assert BaseServiceLocator.get("number") == 42

        # 注册字典
        data = {"key": "value"}
        BaseServiceLocator.register("dict", data)
        assert BaseServiceLocator.get("dict") is data

        # 注册函数
        def test_func():
            return "result"

        BaseServiceLocator.register("func", test_func)
        assert BaseServiceLocator.get("func")() == "result"

    def test_get_or_create_with_lambda(self):
        """测试 get_or_create 使用 lambda"""
        result = BaseServiceLocator.get_or_create("test", lambda: MockService("lambda"))
        assert result.get_name() == "lambda"

    def test_multiple_clear_calls(self):
        """测试多次清除调用"""
        service = MockService("test")
        BaseServiceLocator.register("test", service)

        BaseServiceLocator.clear("test")
        assert BaseServiceLocator.get("test") is None

        # 再次清除不应该抛出异常
        BaseServiceLocator.clear("test")
        assert BaseServiceLocator.get("test") is None

    def test_service_persistence_across_operations(self):
        """测试服务在多次操作中的持久性"""
        service = MockService("persistent")
        BaseServiceLocator.register("test", service)

        # 多次获取应该返回同一个实例
        retrieved1 = BaseServiceLocator.get("test")
        retrieved2 = BaseServiceLocator.get("test")
        retrieved3 = BaseServiceLocator.get("test")

        assert retrieved1 is service
        assert retrieved2 is service
        assert retrieved3 is service

    def test_empty_service_name(self):
        """测试空服务名"""
        service = MockService("empty_name")
        BaseServiceLocator.register("", service)

        retrieved = BaseServiceLocator.get("")
        assert retrieved is service

    def test_service_name_with_special_characters(self):
        """测试包含特殊字符的服务名"""
        service = MockService("special")
        special_names = ["service.name", "service-name", "service_name", "service:name", "service/name", "service@name"]

        for name in special_names:
            BaseServiceLocator.register(name, service)
            assert BaseServiceLocator.get(name) is service
            BaseServiceLocator.clear(name)
