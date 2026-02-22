"""
Service层合规性属性测试

验证automation模块的Service层完全符合四层架构规范：
- Property 6: Service层依赖注入支持
- Property 7: Service层延迟加载使用
- Property 8: Service层事务管理
- Property 9: Service层异常三参数
- Property 10: Service层跨模块调用

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

import ast
import inspect
import re
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
from apps.automation.services.scraper.core.browser_service import BrowserService
from apps.automation.services.scraper.core.monitor_service import MonitorService
from apps.automation.services.scraper.core.security_service import SecurityService
from apps.automation.services.scraper.core.validator_service import ValidatorService
from apps.automation.services.scraper.court_document_service import CourtDocumentService
from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.automation.services.token.cache_manager import TokenCacheManager


class TestServiceLayerCompliance:
    """Service层合规性属性测试"""

    def get_automation_service_classes(self) -> List[type]:
        """获取所有automation模块的Service类"""
        return [
            CaptchaRecognitionService,
            PreservationQuoteService,
            CourtDocumentService,
            AutoTokenAcquisitionService,
            MonitorService,
            ValidatorService,
            TokenCacheManager,
            SecurityService,
            BrowserService,
        ]

    @given(
        st.sampled_from(
            [
                CaptchaRecognitionService,
                PreservationQuoteService,
                CourtDocumentService,
                AutoTokenAcquisitionService,
                MonitorService,
                ValidatorService,
                TokenCacheManager,
                SecurityService,
                BrowserService,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_6_service_dependency_injection_support(self, service_class):
        """
        **Feature: automation-module-compliance, Property 6: Service层依赖注入支持**

        验证Service类构造函数支持可选的依赖注入参数

        For any Service类构造函数，都应该支持可选的依赖注入参数
        **Validates: Requirements 2.1**
        """
        # 获取构造函数签名
        init_signature = inspect.signature(service_class.__init__)
        parameters = list(init_signature.parameters.values())

        # 排除self参数
        non_self_params = [p for p in parameters if p.name != "self"]

        if non_self_params:
            # 如果有参数，验证所有参数都是可选的（有默认值）
            # *args 和 **kwargs 不需要默认值
            for param in non_self_params:
                if param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    assert (
                        param.default is not inspect.Parameter.empty
                    ), f"{service_class.__name__}构造函数参数 '{param.name}' 必须有默认值以支持依赖注入"

        # 验证可以无参数实例化
        try:
            instance = service_class()
            assert instance is not None, f"{service_class.__name__} 必须支持无参数实例化"
        except Exception as e:
            pytest.fail(f"{service_class.__name__} 无参数实例化失败: {e}")

    @given(
        st.sampled_from(
            [
                CaptchaRecognitionService,
                PreservationQuoteService,
                CourtDocumentService,
                AutoTokenAcquisitionService,
                MonitorService,
                ValidatorService,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_7_service_lazy_loading_usage(self, service_class):
        """
        **Feature: automation-module-compliance, Property 7: Service层延迟加载使用**

        验证Service类依赖访问使用@property进行延迟加载

        For any Service类依赖访问，都应该使用@property进行延迟加载
        **Validates: Requirements 2.2**
        """
        # 获取类的所有属性
        class_members = inspect.getmembers(service_class)

        # 查找@property装饰的方法
        property_methods = [name for name, member in class_members if isinstance(member, property)]

        # 检查源代码中的依赖访问模式
        try:
            source = inspect.getsource(service_class)

            # 查找可能的依赖属性模式
            dependency_patterns = [
                r"self\._(\w+_service)",
                r"self\.(\w+_service)",
                r"self\._(\w+_client)",
                r"self\.(\w+_client)",
            ]

            found_dependencies = set()
            for pattern in dependency_patterns:
                matches = re.findall(pattern, source)
                found_dependencies.update(matches)

            # 如果找到依赖，验证是否有对应的@property方法
            for dep in found_dependencies:
                if dep.startswith("_"):
                    # 私有属性，应该有对应的公开property
                    public_name = dep[1:]  # 去掉下划线
                    assert (
                        public_name in property_methods
                    ), f"{service_class.__name__} 的依赖 '{dep}' 应该有对应的 @property 方法 '{public_name}'"

        except (OSError, TypeError):
            # 如果无法获取源代码，跳过此测试
            pass

    @given(
        st.sampled_from(
            [
                PreservationQuoteService,
                CourtDocumentService,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_8_service_transaction_management(self, service_class):
        """
        **Feature: automation-module-compliance, Property 8: Service层事务管理**

        验证Service层业务操作方法使用@transaction.atomic管理事务

        For any Service层业务操作方法，都应该使用@transaction.atomic管理事务
        **Validates: Requirements 2.3**
        """
        # 获取类的所有方法
        methods = inspect.getmembers(service_class, predicate=inspect.isfunction)

        # 查找业务操作方法（create, update, delete等）
        business_method_patterns = [
            r"^create_",
            r"^update_",
            r"^delete_",
            r"^execute_",
            r"^retry_",
        ]

        business_methods = []
        for method_name, method in methods:
            for pattern in business_method_patterns:
                if re.match(pattern, method_name):
                    business_methods.append((method_name, method))
                    break

        # 验证业务方法有@transaction.atomic装饰器
        for method_name, method in business_methods:
            try:
                source = inspect.getsource(method)

                # 检查是否有@transaction.atomic装饰器
                has_transaction_atomic = "@transaction.atomic" in source or "transaction.atomic" in source

                assert (
                    has_transaction_atomic
                ), f"{service_class.__name__}.{method_name} 业务方法必须使用 @transaction.atomic 装饰器"

            except (OSError, TypeError):
                # 如果无法获取源代码，跳过此方法
                continue

    @given(
        st.sampled_from(
            [
                CaptchaRecognitionService,
                PreservationQuoteService,
                CourtDocumentService,
                AutoTokenAcquisitionService,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_9_service_exception_three_parameters(self, service_class):
        """
        **Feature: automation-module-compliance, Property 9: Service层异常三参数**

        验证Service层抛出的业务异常包含message、code、errors三个参数

        For any Service层抛出的业务异常，都应该包含message、code、errors三个参数
        **Validates: Requirements 2.4**
        """
        try:
            source = inspect.getsource(service_class)

            # 查找raise语句
            raise_patterns = [
                r"raise\s+(\w+Exception)\s*\(",
                r"raise\s+(\w+Error)\s*\(",
            ]

            found_exceptions = []
            for pattern in raise_patterns:
                matches = re.finditer(pattern, source)
                for match in matches:
                    # 获取完整的raise语句
                    start_pos = match.start()
                    # 找到raise语句的结束位置
                    paren_count = 0
                    end_pos = start_pos
                    in_raise = False

                    for i, char in enumerate(source[start_pos:], start_pos):
                        if char == "(":
                            paren_count += 1
                            in_raise = True
                        elif char == ")":
                            paren_count -= 1
                            if paren_count == 0 and in_raise:
                                end_pos = i + 1
                                break

                    if end_pos > start_pos:
                        raise_statement = source[start_pos:end_pos]
                        found_exceptions.append(raise_statement)

            # 验证每个异常是否包含三个参数
            for exception_stmt in found_exceptions:
                # 跳过重新抛出的异常（raise without arguments）
                if exception_stmt.strip() == "raise":
                    continue

                # 检查是否包含message、code、errors参数
                has_message = "message=" in exception_stmt
                has_code = "code=" in exception_stmt
                has_errors = "errors=" in exception_stmt

                # 如果是业务异常，必须包含三个参数
                if any(
                    exc_type in exception_stmt
                    for exc_type in [
                        "ValidationException",
                        "NotFoundError",
                        "ConflictError",
                        "BusinessException",
                        "AutoTokenAcquisitionError",
                    ]
                ):
                    assert (
                        has_message and has_code and has_errors
                    ), f"{service_class.__name__} 中的异常必须包含 message、code、errors 三个参数: {exception_stmt}"

        except (OSError, TypeError):
            # 如果无法获取源代码，跳过此测试
            pass

    @given(
        st.sampled_from(
            [
                PreservationQuoteService,
                AutoTokenAcquisitionService,
                MonitorService,
                ValidatorService,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_10_service_cross_module_calls(self, service_class):
        """
        **Feature: automation-module-compliance, Property 10: Service层跨模块调用**

        验证Service层跨模块调用通过ServiceLocator获取服务

        For any Service层跨模块调用，都应该通过ServiceLocator获取服务
        **Validates: Requirements 2.5**
        """
        try:
            source = inspect.getsource(service_class)

            # 检查是否有跨模块直接导入（禁止的模式）
            prohibited_import_patterns = [
                r"from\s+apps\.client\..*import",
                r"from\s+apps\.cases\..*import",
                r"from\s+apps\.contracts\..*import",
                r"from\s+apps\.organization\..*import",
            ]

            for pattern in prohibited_import_patterns:
                matches = re.findall(pattern, source)
                assert not matches, f"{service_class.__name__} 不应该直接导入其他模块: {matches}"

            # 检查是否正确使用ServiceLocator
            if "ServiceLocator" in source:
                # 验证ServiceLocator的使用方式
                servicelocator_pattern = r"ServiceLocator\.get_(\w+_service)\(\)"
                matches = re.findall(servicelocator_pattern, source)

                # 如果使用了ServiceLocator，验证调用模式正确
                if matches:
                    # 验证导入语句正确
                    correct_import = "from apps.core.interfaces import ServiceLocator"
                    assert (
                        correct_import in source
                    ), f"{service_class.__name__} 必须正确导入 ServiceLocator: {correct_import}"

        except (OSError, TypeError):
            # 如果无法获取源代码，跳过此测试
            pass

    def test_service_layer_comprehensive_compliance_check(self):
        """
        Service层综合合规性检查

        验证所有Service类的整体合规性
        """
        service_classes = self.get_automation_service_classes()

        compliance_report = {"total_services": len(service_classes), "compliant_services": 0, "violations": []}

        for service_class in service_classes:
            violations = []

            # 检查1: 构造函数依赖注入支持
            try:
                init_signature = inspect.signature(service_class.__init__)  # type: ignore[misc]
                parameters = list(init_signature.parameters.values())
                non_self_params = [p for p in parameters if p.name != "self"]

                for param in non_self_params:
                    if param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                        if param.default is inspect.Parameter.empty:
                            violations.append(f"构造函数参数 '{param.name}' 缺少默认值")

                # 测试无参数实例化
                service_class()

            except Exception as e:
                violations.append(f"构造函数依赖注入不合规: {e}")

            # 检查2: @property延迟加载
            try:
                source = inspect.getsource(service_class)
                if "_service" in source or "_client" in source:
                    class_members = inspect.getmembers(service_class)
                    property_methods = [name for name, member in class_members if isinstance(member, property)]

                    if not property_methods:
                        violations.append("缺少 @property 延迟加载方法")

            except (OSError, TypeError):
                pass

            # 检查3: 事务管理
            try:
                source = inspect.getsource(service_class)
                methods = inspect.getmembers(service_class, predicate=inspect.isfunction)

                # 只检查数据库相关的Service类的事务管理
                if service_class.__name__ in ["PreservationQuoteService", "CourtDocumentService"]:
                    business_methods = [
                        name
                        for name, _ in methods
                        if any(name.startswith(prefix) for prefix in ["create_", "update_", "delete_", "execute_"])
                    ]

                    for method_name in business_methods:
                        method_source = inspect.getsource(getattr(service_class, method_name))
                        if "@transaction.atomic" not in method_source:
                            violations.append(f"业务方法 '{method_name}' 缺少 @transaction.atomic")

            except (OSError, TypeError):
                pass

            # 记录结果
            if not violations:
                compliance_report["compliant_services"] += 1  # type: ignore[operator]
            else:
                compliance_report["violations"].append({"service": service_class.__name__, "violations": violations})  # type: ignore[attr-defined]

        # 计算合规率
        compliance_rate = (
            compliance_report["compliant_services"] / compliance_report["total_services"] * 100  # type: ignore[operator]
            if compliance_report["total_services"] > 0  # type: ignore[operator]
            else 0
        )

        # 输出合规性报告
        print(f"\n=== Service层合规性报告 ===")
        print(f"总Service数: {compliance_report['total_services']}")
        print(f"合规Service数: {compliance_report['compliant_services']}")
        print(f"合规率: {compliance_rate:.1f}%")

        if compliance_report["violations"]:
            print(f"\n违规详情:")
            for violation in compliance_report["violations"]:  # type: ignore[attr-defined]
                print(f"  {violation['service']}:")
                for v in violation["violations"]:
                    print(f"    - {v}")

        # 要求至少80%的合规率
        assert compliance_rate >= 80.0, (
            f"Service层合规率 {compliance_rate:.1f}% 低于要求的80%。"
            f"违规Service: {[v['service'] for v in compliance_report['violations']]}"  # type: ignore[attr-defined]
        )


@composite
def service_method_source(draw):
    """生成Service方法源代码的策略"""
    method_names = draw(
        st.sampled_from(
            [
                "create_client",
                "update_client",
                "delete_client",
                "create_case",
                "update_case",
                "execute_task",
                "get_data",
                "list_items",
                "process_request",
            ]
        )
    )

    has_transaction = draw(st.booleans())
    has_exception = draw(st.booleans())

    source_parts = []

    if has_transaction:
        source_parts.append("@transaction.atomic")

    source_parts.append(f"def {method_names}(self):")
    source_parts.append("    pass")

    if has_exception:
        exception_type = draw(st.sampled_from(["ValidationException", "NotFoundError", "ConflictError"]))
        source_parts.append(f"    raise {exception_type}(message='test', code='TEST', errors={{}})")

    return "\n".join(source_parts)


class TestServiceLayerPropertyBasedCompliance:
    """基于属性的Service层合规性测试"""

    @given(service_method_source())
    @settings(max_examples=50)
    def test_service_method_compliance_patterns(self, method_source):
        """
        测试Service方法的合规性模式

        验证生成的Service方法代码符合规范要求
        """
        # 解析方法源代码
        try:
            tree = ast.parse(method_source)
        except SyntaxError:
            assume(False)  # 跳过无效的源代码

        # 检查方法定义
        method_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert len(method_defs) >= 1, "必须包含至少一个方法定义"

        for method_def in method_defs:
            method_name = method_def.name

            # 检查业务方法的事务装饰器
            if any(method_name.startswith(prefix) for prefix in ["create_", "update_", "delete_", "execute_"]):
                # 如果源代码中有@transaction.atomic，验证AST中也有对应的装饰器
                if "@transaction.atomic" in method_source:
                    # 检查装饰器 - 更准确的AST检查
                    has_transaction = False
                    for decorator in method_def.decorator_list:
                        if hasattr(decorator, "attr") and decorator.attr == "atomic":
                            has_transaction = True
                            break
                        elif hasattr(decorator, "id") and "atomic" in decorator.id:
                            has_transaction = True
                            break
                        elif "transaction" in str(decorator):
                            has_transaction = True
                            break

                    assert has_transaction, f"业务方法 {method_name} 应该有 @transaction.atomic 装饰器"

            # 检查异常抛出
            for node in ast.walk(method_def):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    if hasattr(node.exc.func, "id"):
                        exc_name = node.exc.func.id
                        if exc_name in ["ValidationException", "NotFoundError", "ConflictError"]:
                            # 检查异常参数
                            keywords = {kw.arg for kw in node.exc.keywords}
                            required_params = {"message", "code", "errors"}

                            assert required_params.issubset(
                                keywords
                            ), f"异常 {exc_name} 必须包含 message、code、errors 参数"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
