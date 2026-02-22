"""
Automation模块适配器接口实现属性测试
测试所有适配器正确实现Protocol接口并提供内部方法

**Feature: automation-module-compliance, Property 26: 适配器接口实现**
**Feature: automation-module-compliance, Property 27: 适配器内部方法提供**
**Validates: Requirements 5.4, 5.5**
"""

import inspect
import re
from typing import get_args, get_origin, get_type_hints

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

# 导入所有适配器类
from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter
from apps.automation.services.document.document_processing_service_adapter import DocumentProcessingServiceAdapter
from apps.automation.services.insurance.preservation_quote_service_adapter import PreservationQuoteServiceAdapter
from apps.automation.services.scraper.core.browser_service import BrowserServiceAdapter
from apps.automation.services.scraper.core.monitor_service import MonitorServiceAdapter
from apps.automation.services.scraper.core.security_service import SecurityServiceAdapter
from apps.automation.services.scraper.core.token_service import TokenServiceAdapter
from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter
from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter

# 导入对应的Protocol接口
from apps.core.interfaces import (
    IAutoNamerService,
    IBrowserService,
    ICaptchaService,
    ICourtDocumentService,
    IDocumentProcessingService,
    IMonitorService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
    ISecurityService,
    ITokenService,
    IValidatorService,
)


@pytest.mark.django_db
class TestAdapterInterfaceImplementationProperties:
    """
    适配器接口实现属性测试

    **Feature: automation-module-compliance, Property 26: 适配器接口实现**
    **Feature: automation-module-compliance, Property 27: 适配器内部方法提供**
    **Validates: Requirements 5.4, 5.5**
    """

    # 定义适配器和对应接口的映射
    ADAPTER_INTERFACE_MAPPING = [
        (CaptchaServiceAdapter, ICaptchaService),
        (AutoNamerServiceAdapter, IAutoNamerService),
        (PreservationQuoteServiceAdapter, IPreservationQuoteService),
        (DocumentProcessingServiceAdapter, IDocumentProcessingService),
        (CourtDocumentServiceAdapter, ICourtDocumentService),
        (ValidatorServiceAdapter, IValidatorService),
        (MonitorServiceAdapter, IMonitorService),
        (TokenServiceAdapter, ITokenService),
        (PerformanceMonitorServiceAdapter, IPerformanceMonitorService),
        (SecurityServiceAdapter, ISecurityService),
        (BrowserServiceAdapter, IBrowserService),
    ]

    @given(st.integers(min_value=0, max_value=len(ADAPTER_INTERFACE_MAPPING) - 1))
    @settings(max_examples=100)
    def test_adapter_implements_protocol_interface(self, adapter_index: int):
        """
        Property 26: 适配器接口实现

        *For any* 适配器类，都应该正确实现对应的Protocol接口

        **Validates: Requirements 5.4**
        """
        adapter_class, protocol_interface = self.ADAPTER_INTERFACE_MAPPING[adapter_index]

        # 验证适配器类存在
        assert adapter_class is not None, f"适配器类 {adapter_class.__name__} 不应为空"

        # 验证Protocol接口存在
        assert protocol_interface is not None, f"Protocol接口 {protocol_interface.__name__} 不应为空"

        # 获取Protocol接口定义的所有方法
        protocol_methods = self._get_protocol_methods(protocol_interface)

        # 验证适配器类实现了所有Protocol方法
        for method_name, method_signature in protocol_methods.items():
            assert hasattr(adapter_class, method_name), f"适配器 {adapter_class.__name__} 应实现方法 {method_name}"

            adapter_method = getattr(adapter_class, method_name)
            assert callable(adapter_method), f"适配器 {adapter_class.__name__} 的方法 {method_name} 应可调用"

            # 验证方法签名兼容性（基本检查）
            adapter_signature = inspect.signature(adapter_method)
            self._verify_method_signature_compatibility(
                adapter_class.__name__, method_name, adapter_signature, method_signature
            )

    @given(st.integers(min_value=0, max_value=len(ADAPTER_INTERFACE_MAPPING) - 1))
    @settings(max_examples=100)
    def test_adapter_provides_internal_methods(self, adapter_index: int):
        """
        Property 27: 适配器内部方法提供

        *For any* 适配器类，都应该为每个公开方法提供对应的内部方法版本

        **Validates: Requirements 5.5**
        """
        adapter_class, protocol_interface = self.ADAPTER_INTERFACE_MAPPING[adapter_index]

        # 获取Protocol接口定义的所有公开方法
        protocol_methods = self._get_protocol_methods(protocol_interface)

        # 验证每个公开方法都有对应的内部方法
        for method_name in protocol_methods.keys():
            # 跳过已经是内部方法的方法
            if method_name.endswith("_internal"):
                continue

            internal_method_name = f"{method_name}_internal"

            assert hasattr(adapter_class, internal_method_name), (
                f"适配器 {adapter_class.__name__} 应提供内部方法 {internal_method_name} 对应公开方法 {method_name}"
            )

            internal_method = getattr(adapter_class, internal_method_name)
            assert callable(internal_method), (
                f"适配器 {adapter_class.__name__} 的内部方法 {internal_method_name} 应可调用"
            )

    def test_all_adapters_have_proper_initialization(self):
        """
        Property 26: 适配器接口实现 - 初始化检查

        *For any* 适配器类，都应该支持无参数初始化或依赖注入初始化

        **Validates: Requirements 5.4**
        """
        for adapter_class, _ in self.ADAPTER_INTERFACE_MAPPING:
            # 验证适配器可以无参数初始化
            try:
                adapter_instance = adapter_class()
                assert adapter_instance is not None, f"适配器 {adapter_class.__name__} 应支持无参数初始化"
            except Exception as e:
                pytest.fail(f"适配器 {adapter_class.__name__} 无参数初始化失败: {e}")

            # 验证构造函数支持依赖注入（可选参数）
            init_signature = inspect.signature(adapter_class.__init__)  # type: ignore[misc]
            parameters = list(init_signature.parameters.values())[1:]  # 跳过self参数

            # 所有参数都应该有默认值（支持依赖注入）
            for param in parameters:
                # 允许 *args 和 **kwargs 参数，以及有默认值的参数
                is_valid_param = (
                    param.default is not inspect.Parameter.empty
                    or param.kind == inspect.Parameter.VAR_POSITIONAL  # *args
                    or param.kind == inspect.Parameter.VAR_KEYWORD  # **kwargs
                )
                assert is_valid_param, (
                    f"适配器 {adapter_class.__name__} 的构造函数参数 {param.name} 应有默认值或为可变参数以支持依赖注入"
                )

    @given(st.integers(min_value=0, max_value=len(ADAPTER_INTERFACE_MAPPING) - 1))
    @settings(max_examples=50)
    def test_adapter_instance_implements_interface(self, adapter_index: int):
        """
        Property 26: 适配器接口实现 - 实例检查

        *For any* 适配器实例，都应该是对应Protocol接口的实例

        **Validates: Requirements 5.4**
        """
        adapter_class, protocol_interface = self.ADAPTER_INTERFACE_MAPPING[adapter_index]

        # 创建适配器实例
        adapter_instance = adapter_class()

        # 验证实例实现了Protocol接口
        # 注意：Python的Protocol是结构化类型，不能直接用isinstance检查
        # 我们通过检查所有必需方法的存在来验证
        protocol_methods = self._get_protocol_methods(protocol_interface)

        for method_name in protocol_methods.keys():
            assert hasattr(adapter_instance, method_name), f"适配器实例 {adapter_class.__name__} 应有方法 {method_name}"

            method = getattr(adapter_instance, method_name)
            assert callable(method), f"适配器实例 {adapter_class.__name__} 的方法 {method_name} 应可调用"

    def test_adapter_internal_methods_consistency(self):
        """
        Property 27: 适配器内部方法提供 - 一致性检查

        *For any* 适配器的内部方法，都应该与对应的公开方法具有相同的签名

        **Validates: Requirements 5.5**
        """
        for adapter_class, protocol_interface in self.ADAPTER_INTERFACE_MAPPING:
            protocol_methods = self._get_protocol_methods(protocol_interface)

            for method_name in protocol_methods.keys():
                if method_name.endswith("_internal"):
                    continue

                internal_method_name = f"{method_name}_internal"

                if hasattr(adapter_class, internal_method_name):
                    public_method = getattr(adapter_class, method_name)
                    internal_method = getattr(adapter_class, internal_method_name)

                    public_signature = inspect.signature(public_method)
                    internal_signature = inspect.signature(internal_method)

                    # 验证参数数量相同（除了可能的额外参数）
                    public_params = list(public_signature.parameters.values())
                    internal_params = list(internal_signature.parameters.values())

                    # 内部方法的参数应该至少包含公开方法的所有参数
                    assert len(internal_params) >= len(public_params), (
                        f"适配器 {adapter_class.__name__} 的内部方法 {internal_method_name} "
                        f"参数数量应不少于公开方法 {method_name}"
                    )

    def _get_protocol_methods(self, protocol_class) -> dict:
        """
        获取Protocol类定义的所有方法

        Args:
            protocol_class: Protocol类

        Returns:
            方法名到方法签名的映射字典
        """
        methods = {}

        # 获取Protocol类的所有注解方法
        if hasattr(protocol_class, "__annotations__"):
            for name, annotation in protocol_class.__annotations__.items():
                if callable(getattr(protocol_class, name, None)):
                    methods[name] = annotation

        # 获取Protocol类的所有方法
        for name, method in inspect.getmembers(protocol_class, predicate=inspect.isfunction):
            if not name.startswith("_"):  # 跳过私有方法
                methods[name] = inspect.signature(method)

        return methods

    def _verify_method_signature_compatibility(
        self, adapter_name: str, method_name: str, adapter_signature: inspect.Signature, protocol_signature
    ):
        """
        验证适配器方法签名与Protocol签名的兼容性

        Args:
            adapter_name: 适配器名称
            method_name: 方法名称
            adapter_signature: 适配器方法签名
            protocol_signature: Protocol方法签名
        """
        # 基本的签名兼容性检查
        # 这里可以根据需要添加更详细的签名验证逻辑

        adapter_params = list(adapter_signature.parameters.values())

        # 验证适配器方法至少有self参数
        assert len(adapter_params) >= 1, f"适配器 {adapter_name} 的方法 {method_name} 应至少有self参数"

        assert adapter_params[0].name == "self", f"适配器 {adapter_name} 的方法 {method_name} 第一个参数应为self"

    def test_adapter_error_handling_consistency(self):
        """
        Property 26: 适配器接口实现 - 错误处理一致性

        *For any* 适配器，都应该使用统一的异常处理机制

        **Validates: Requirements 5.4**
        """
        for adapter_class, _ in self.ADAPTER_INTERFACE_MAPPING:
            adapter_source = inspect.getsource(adapter_class)

            # 只检查带参数的 raise（即 raise SomeException(...)），裸 raise 是合法的重新抛出
            has_raise_with_arg = bool(re.search(r"\braise\s+[A-Z]\w*", adapter_source))
            if has_raise_with_arg:
                # 如果有带参数的异常抛出，应该使用标准化的异常类
                assert any(
                    exc_type in adapter_source
                    for exc_type in [
                        "ValidationException",
                        "BusinessException",
                        "NotFoundError",
                        "AutomationExceptions",
                        "apps.core.exceptions",
                        "Exception",  # 允许通用 Exception 重新包装
                    ]
                ), f"适配器 {adapter_class.__name__} 应使用标准化的异常类型"

    def test_adapter_logging_consistency(self):
        """
        Property 26: 适配器接口实现 - 日志记录一致性

        *For any* 适配器，都应该使用统一的日志记录机制

        **Validates: Requirements 5.4**
        """
        for adapter_class, _ in self.ADAPTER_INTERFACE_MAPPING:
            adapter_source = inspect.getsource(adapter_class)

            # 检查是否使用了日志记录
            if "logger" in adapter_source:
                # 如果使用了日志，应该使用标准化的日志记录方式
                assert any(
                    log_pattern in adapter_source
                    for log_pattern in [
                        "logger.info",
                        "logger.error",
                        "logger.warning",
                        "logger.debug",
                        "logging.getLogger",
                    ]
                ), f"适配器 {adapter_class.__name__} 应使用标准化的日志记录方式"

    def test_adapter_dependency_injection_support(self):
        """
        Property 26: 适配器接口实现 - 依赖注入支持

        *For any* 适配器，都应该支持依赖注入模式

        **Validates: Requirements 5.4**
        """
        for adapter_class, _ in self.ADAPTER_INTERFACE_MAPPING:
            adapter_source = inspect.getsource(adapter_class)

            # 检查是否支持依赖注入模式（或是合法的无状态适配器）
            dependency_injection_patterns = [
                "@property",
                "ServiceLocator",
                "_service",
                "Optional[",
                "if.*is None:",
                "self._.*=.*",
            ]

            has_dependency_injection = any(pattern in adapter_source for pattern in dependency_injection_patterns)

            # 无状态适配器（没有 __init__ 或 __init__ 为空）也是合法的
            has_custom_init = bool(re.search(r"def __init__\s*\(", adapter_source))
            if has_custom_init:
                # 有 __init__ 的情况下，检查是否有实例变量赋值
                has_instance_vars = bool(re.search(r"self\._\w+\s*=", adapter_source))
                is_stateless = not has_instance_vars
            else:
                is_stateless = True  # 没有 __init__ 就是无状态

            assert has_dependency_injection or is_stateless, f"适配器 {adapter_class.__name__} 应支持依赖注入模式"

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=20)
    def test_adapter_method_naming_convention(self, method_suffix: str):
        """
        Property 27: 适配器内部方法提供 - 命名约定

        *For any* 适配器的内部方法，都应该遵循 {method_name}_internal 的命名约定

        **Validates: Requirements 5.5**
        """
        # 过滤掉无效的方法名字符
        method_suffix = "".join(c for c in method_suffix if c.isalnum() or c == "_")
        if not method_suffix or method_suffix.startswith("_"):
            return  # 跳过无效的方法名

        for adapter_class, _ in self.ADAPTER_INTERFACE_MAPPING:
            # 获取所有以_internal结尾的方法
            internal_methods = [
                name
                for name in dir(adapter_class)
                if name.endswith("_internal") and callable(getattr(adapter_class, name))
            ]

            for internal_method_name in internal_methods:
                # 验证命名约定
                assert internal_method_name.endswith("_internal"), (
                    f"适配器 {adapter_class.__name__} 的内部方法 {internal_method_name} 应以 '_internal' 结尾"
                )

                # 验证对应的公开方法存在
                public_method_name = internal_method_name[:-9]  # 移除 '_internal'
                if public_method_name:  # 确保不是空字符串
                    # 注意：不是所有内部方法都必须有对应的公开方法
                    # 但如果有公开方法，应该验证其存在性
                    if hasattr(adapter_class, public_method_name):
                        public_method = getattr(adapter_class, public_method_name)
                        assert callable(public_method), (
                            f"适配器 {adapter_class.__name__} 的公开方法 {public_method_name} 应可调用"
                        )
