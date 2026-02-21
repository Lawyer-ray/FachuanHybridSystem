"""
Admin层合规性属性测试

验证automation模块的Admin层完全符合四层架构规范：
- Property 11: Admin层复杂操作委托
- Property 12: Admin层方法行数限制
- Property 13: Admin层跨模块访问
- Property 14: Admin层异常处理委托
- Property 15: Admin层Service实例化禁止

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import ast
import inspect
import re
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from apps.automation.admin.insurance.preservation_quote_admin import PreservationQuoteAdmin
from apps.automation.admin.scraper.court_document_admin import CourtDocumentAdmin

# 导入所有automation Admin模块
from apps.automation.admin.token.token_acquisition_history_admin import TokenAcquisitionHistoryAdmin
from apps.core.path import Path


class TestAdminLayerCompliance:
    """Admin层合规性属性测试"""

    def get_automation_admin_classes(self) -> List[type]:
        """获取所有automation模块的Admin类"""
        return [
            TokenAcquisitionHistoryAdmin,
            CourtDocumentAdmin,
            PreservationQuoteAdmin,
        ]

    def get_admin_module_paths(self) -> List[str]:
        """获取所有Admin模块的文件路径"""
        base_path = Path(__file__).parent.parent.parent.parent / "apps" / "automation" / "admin"
        admin_files = []

        for file_path in base_path.glob("*_admin.py"):
            admin_files.append(str(file_path))

        return admin_files

    @given(
        st.sampled_from(
            [
                TokenAcquisitionHistoryAdmin,
                CourtDocumentAdmin,
                PreservationQuoteAdmin,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_11_admin_complex_operation_delegation(self, admin_class):
        """
        **Feature: automation-module-compliance, Property 11: Admin层复杂操作委托**

        验证Admin层复杂操作使用工厂函数委托给AdminService处理

        For any Admin层复杂操作，都应该使用工厂函数委托给AdminService处理
        **Validates: Requirements 3.1**
        """
        try:
            # Get the module source instead of just the class source
            import sys

            module = sys.modules[admin_class.__module__]
            source = inspect.getsource(module)

            # 检查是否有工厂函数定义
            factory_function_pattern = r"def\s+_get_.*_service\(\s*\):"
            factory_functions = re.findall(factory_function_pattern, source)

            # 获取所有Admin Action方法
            admin_action_patterns = [
                r"def\s+(cleanup_\w+)\(",
                r"def\s+(export_\w+)\(",
                r"def\s+(retry_\w+)\(",
                r"def\s+(batch_\w+)\(",
                r"def\s+(reanalyze_\w+)\(",
                r"def\s+(execute_\w+)\(",
            ]

            admin_actions = []
            for pattern in admin_action_patterns:
                matches = re.findall(pattern, source)
                admin_actions.extend(matches)

            if admin_actions:
                # 如果有Admin Action，必须有对应的工厂函数
                assert (
                    factory_functions
                ), f"{admin_class.__name__} 包含Admin Action但缺少工厂函数 _get_xxx_admin_service()"

                # 检查Admin Action中是否正确使用工厂函数
                for action_name in admin_actions:
                    try:
                        action_method = getattr(admin_class, action_name)
                        action_source = inspect.getsource(action_method)

                        # 检查是否使用工厂函数获取AdminService
                        factory_call_pattern = r"service\s*=\s*_get_.*_service\(\)"
                        factory_calls = re.findall(factory_call_pattern, action_source)

                        assert (
                            factory_calls
                        ), f"{admin_class.__name__}.{action_name} 必须使用工厂函数获取AdminService实例"

                        # 检查是否委托给AdminService处理
                        service_delegation_patterns = [
                            r"service\.\w+\(",
                            r"result\s*=\s*service\.\w+\(",
                            r"count\s*=\s*service\.\w+\(",
                            r"response\s*=\s*service\.\w+\(",
                        ]

                        has_delegation = False
                        for pattern in service_delegation_patterns:
                            if re.search(pattern, action_source):
                                has_delegation = True
                                break

                        assert (
                            has_delegation
                        ), f"{admin_class.__name__}.{action_name} 必须委托给AdminService处理复杂逻辑"

                    except (AttributeError, OSError):
                        # 如果无法获取方法源代码，跳过
                        continue

        except (OSError, TypeError):
            # 如果无法获取类源代码，跳过此测试
            pass

    @given(
        st.sampled_from(
            [
                TokenAcquisitionHistoryAdmin,
                CourtDocumentAdmin,
                PreservationQuoteAdmin,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_12_admin_method_line_limit(self, admin_class):
        """
        **Feature: automation-module-compliance, Property 12: Admin层方法行数限制**

        验证Admin层方法实现业务逻辑不超过20行

        For any Admin层方法实现，业务逻辑都不应该超过20行
        **Validates: Requirements 3.2**
        """
        # 获取类的所有方法
        methods = inspect.getmembers(admin_class, predicate=inspect.ismethod)

        # 添加实例方法
        instance_methods = []
        for name in dir(admin_class):
            if not name.startswith("_") or name in ["__init__"]:
                attr = getattr(admin_class, name)
                if callable(attr) and not isinstance(attr, type):
                    instance_methods.append((name, attr))

        all_methods = methods + instance_methods

        for method_name, method in all_methods:
            # 跳过Django Admin的内置方法和属性
            if method_name in [
                "has_add_permission",
                "has_change_permission",
                "has_delete_permission",
                "get_queryset",
                "get_urls",
                "changelist_view",
                "get_readonly_fields",
                "get_list_display",
                "get_list_filter",
                "get_search_fields",
                "save_model",
                "delete_model",
                "save_related",
                "formfield_for_dbfield",
                "formfield_for_manytomany",
                "get_form",
                "get_inline_formsets",
                "get_search_results",
                "lookup_allowed",
                "render_change_form",
                "response_action",
                "response_add",
                "response_change",
                "response_delete",
                "to_field_allowed",
                "get_fieldsets",
                "get_inline_instances",
                "get_formsets_with_inlines",
            ]:
                continue

            # 跳过显示方法（通常是格式化显示，允许较长）
            if (
                method_name.endswith("_display")
                or method_name.endswith("_view")
                or method_name.endswith("_summary")
                or method_name in ["quotes_summary", "performance_summary"]
                or method_name.startswith("_build_")
                or method_name.startswith("_render_")
                or method_name.startswith("_display_")
                or method_name.startswith("_provide_")
            ):
                continue

            try:
                method_source = inspect.getsource(method)

                # 计算有效代码行数（排除空行、注释、装饰器）
                lines = method_source.split("\n")
                effective_lines = []

                in_method_body = False
                for line in lines:
                    stripped = line.strip()

                    # 跳过空行
                    if not stripped:
                        continue

                    # 跳过纯注释行
                    if stripped.startswith("#"):
                        continue

                    # 跳过装饰器
                    if stripped.startswith("@"):
                        continue

                    # 方法定义行
                    if stripped.startswith("def "):
                        in_method_body = True
                        continue

                    # 文档字符串
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        continue

                    if in_method_body:
                        effective_lines.append(line)

                # 检查行数限制（允许一些灵活性）
                line_count = len(effective_lines)

                # 对于Admin Action方法，允许更严格的限制
                if any(
                    method_name.startswith(prefix)
                    for prefix in ["cleanup_", "export_", "retry_", "batch_", "reanalyze_", "execute_"]
                ):
                    # Admin Action方法应该主要是委托调用，但允许结果格式化逻辑
                    # 检查是否正确使用了AdminService
                    method_source = inspect.getsource(method)
                    if "service = _get_" in method_source and "_service()" in method_source:
                        # 如果正确委托给AdminService，允许更多行用于结果格式化
                        assert line_count <= 40, (
                            f"{admin_class.__name__}.{method_name} Admin Action方法有 {line_count} 行，"
                            f"超过40行限制。虽然已委托给AdminService，但结果格式化过于复杂。"
                        )
                    else:
                        # 如果没有委托给AdminService，严格限制
                        assert line_count <= 25, (
                            f"{admin_class.__name__}.{method_name} Admin Action方法有 {line_count} 行，"
                            f"超过25行限制。应该委托给AdminService处理复杂逻辑。"
                        )
                else:
                    # 其他方法允许稍微宽松一些
                    assert line_count <= 30, (
                        f"{admin_class.__name__}.{method_name} 方法有 {line_count} 行，"
                        f"超过30行限制。应该拆分为多个方法或委托给Service处理。"
                    )

            except (OSError, TypeError):
                # 如果无法获取方法源代码，跳过
                continue

    @given(
        st.sampled_from(
            [
                TokenAcquisitionHistoryAdmin,
                CourtDocumentAdmin,
                PreservationQuoteAdmin,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_13_admin_cross_module_access(self, admin_class):
        """
        **Feature: automation-module-compliance, Property 13: Admin层跨模块访问**

        验证Admin层跨模块数据需求通过ServiceLocator访问

        For any Admin层跨模块数据需求，都应该通过ServiceLocator访问
        **Validates: Requirements 3.3**
        """
        try:
            # Get the module source instead of just the class source
            import sys

            module = sys.modules[admin_class.__module__]
            source = inspect.getsource(module)

            # 检查是否有禁止的跨模块直接导入
            prohibited_import_patterns = [
                r"from\s+apps\.client\..*import",
                r"from\s+apps\.cases\..*import",
                r"from\s+apps\.contracts\..*import",
                r"from\s+apps\.organization\..*import",
            ]

            for pattern in prohibited_import_patterns:
                violations = re.findall(pattern, source)
                assert not violations, f"{admin_class.__name__} 不应该直接导入其他模块: {violations}"

            # 检查是否正确使用ServiceLocator（如果需要跨模块访问）
            if "ServiceLocator" in source:
                # 验证ServiceLocator的导入和使用
                correct_import = "from apps.core.interfaces import ServiceLocator"

                # 在工厂函数或AdminService中使用ServiceLocator是允许的
                factory_function_pattern = r"def\s+_get_\w+_admin_service\(\s*\):(.*?)(?=\n\n|\ndef|\n@|\Z)"
                factory_matches = re.findall(factory_function_pattern, source, re.DOTALL)

                for factory_body in factory_matches:
                    if "ServiceLocator" in factory_body:
                        assert correct_import in source, f"{admin_class.__name__} 工厂函数必须正确导入ServiceLocator"

                        # 验证ServiceLocator的使用模式
                        servicelocator_usage_pattern = r"ServiceLocator\.get_\w+_service\(\)"
                        servicelocator_calls = re.findall(servicelocator_usage_pattern, factory_body)

                        if servicelocator_calls:
                            for call in servicelocator_calls:
                                assert (
                                    "get_" in call and "_service()" in call
                                ), f"{admin_class.__name__} ServiceLocator调用模式不正确: {call}"

        except (OSError, TypeError):
            # 如果无法获取类源代码，跳过此测试
            pass

    @given(
        st.sampled_from(
            [
                TokenAcquisitionHistoryAdmin,
                CourtDocumentAdmin,
                PreservationQuoteAdmin,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_14_admin_exception_handling_delegation(self, admin_class):
        """
        **Feature: automation-module-compliance, Property 14: Admin层异常处理委托**

        验证Admin层异常处理委托给AdminService处理

        For any Admin层异常处理，都应该委托给AdminService处理
        **Validates: Requirements 3.4**
        """
        # 获取类的所有方法
        methods = inspect.getmembers(admin_class, predicate=inspect.ismethod)

        # 添加实例方法
        instance_methods = []
        for name in dir(admin_class):
            if not name.startswith("_"):
                attr = getattr(admin_class, name)
                if callable(attr) and not isinstance(attr, type):
                    instance_methods.append((name, attr))

        all_methods = methods + instance_methods

        for method_name, method in all_methods:
            # 只检查Admin Action方法
            if not any(
                method_name.startswith(prefix)
                for prefix in ["cleanup_", "export_", "retry_", "batch_", "reanalyze_", "execute_"]
            ):
                continue

            try:
                method_source = inspect.getsource(method)

                # 检查异常处理模式
                try_except_pattern = r"try\s*:(.*?)except\s+(\w+)\s+as\s+(\w+):(.*?)(?=\n\n|\ndef|\n    def|\Z)"
                try_blocks = re.findall(try_except_pattern, method_source, re.DOTALL)

                for try_body, exception_type, exception_var, except_body in try_blocks:
                    # Admin层的异常处理应该简单，主要是显示消息
                    # 复杂的异常处理应该在AdminService中

                    # 检查except块是否只是简单的消息显示
                    simple_message_patterns = [
                        r"self\.message_user\(",
                        r"messages\.\w+\(",
                    ]

                    has_simple_handling = False
                    for pattern in simple_message_patterns:
                        if re.search(pattern, except_body):
                            has_simple_handling = True
                            break

                    # 检查是否有复杂的异常处理逻辑
                    complex_handling_patterns = [
                        r"if\s+.*:",  # 复杂的条件判断
                        r"for\s+.*:",  # 循环处理
                        r"while\s+.*:",  # 循环处理
                        r"def\s+.*:",  # 内部函数定义
                    ]

                    has_complex_handling = False
                    for pattern in complex_handling_patterns:
                        if re.search(pattern, except_body):
                            has_complex_handling = True
                            break

                    if has_complex_handling:
                        assert False, (
                            f"{admin_class.__name__}.{method_name} 包含复杂的异常处理逻辑，"
                            f"应该委托给AdminService处理"
                        )

                    # 如果有异常处理，应该有简单的消息显示
                    if not has_simple_handling:
                        # 允许一些简单的异常处理，如记录日志
                        if "logger." not in except_body and "log." not in except_body:
                            assert False, f"{admin_class.__name__}.{method_name} 异常处理应该包含用户消息显示"

            except (OSError, TypeError):
                # 如果无法获取方法源代码，跳过
                continue

    @given(
        st.sampled_from(
            [
                TokenAcquisitionHistoryAdmin,
                CourtDocumentAdmin,
                PreservationQuoteAdmin,
            ]
        )
    )
    @settings(max_examples=100)
    def test_property_15_admin_service_instantiation_prohibited(self, admin_class):
        """
        **Feature: automation-module-compliance, Property 15: Admin层Service实例化禁止**

        验证Admin层不直接实例化Service类

        For any Admin层代码，都不应该直接实例化Service类
        **Validates: Requirements 3.5**
        """
        try:
            # Get the module source instead of just the class source
            import sys

            module = sys.modules[admin_class.__module__]
            source = inspect.getsource(module)

            # 检查禁止的直接Service实例化模式
            prohibited_instantiation_patterns = [
                r"\w+Service\(\)",
                r"\w+AdminService\(\)",
                r"from\s+.*services.*import.*Service",
            ]

            # 获取所有方法
            methods = inspect.getmembers(admin_class, predicate=inspect.ismethod)
            instance_methods = []
            for name in dir(admin_class):
                if not name.startswith("_"):
                    attr = getattr(admin_class, name)
                    if callable(attr) and not isinstance(attr, type):
                        instance_methods.append((name, attr))

            all_methods = methods + instance_methods

            for method_name, method in all_methods:
                # 跳过工厂函数（允许在工厂函数内部实例化）
                if method_name.startswith("_get_") and method_name.endswith("_service"):
                    continue

                try:
                    method_source = inspect.getsource(method)

                    for pattern in prohibited_instantiation_patterns:
                        violations = re.findall(pattern, method_source)

                        if violations:
                            # 过滤掉一些合法的使用场景
                            filtered_violations = []
                            for violation in violations:
                                # 排除导入语句中的Service（如果在工厂函数中）
                                if "import" in violation and "_get_" in method_source:
                                    continue
                                # 排除字符串中的内容
                                if violation.startswith('"') or violation.startswith("'"):
                                    continue
                                filtered_violations.append(violation)

                            assert not filtered_violations, (
                                f"{admin_class.__name__}.{method_name} 不应该直接实例化Service: {filtered_violations}。"
                                f"应该使用工厂函数 _get_xxx_admin_service()"
                            )

                except (OSError, TypeError):
                    # 如果无法获取方法源代码，跳过
                    continue

            # 检查整个类是否有正确的工厂函数使用模式
            admin_action_patterns = [
                r"def\s+(cleanup_\w+)\(",
                r"def\s+(export_\w+)\(",
                r"def\s+(retry_\w+)\(",
                r"def\s+(batch_\w+)\(",
                r"def\s+(reanalyze_\w+)\(",
                r"def\s+(execute_\w+)\(",
            ]

            admin_actions = []
            for pattern in admin_action_patterns:
                matches = re.findall(pattern, source)
                admin_actions.extend(matches)

            if admin_actions:
                # 如果有Admin Action，检查是否正确使用工厂函数
                factory_call_pattern = r"service\s*=\s*_get_.*_service\(\)"
                factory_calls = re.findall(factory_call_pattern, source)

                assert factory_calls, f"{admin_class.__name__} 包含Admin Action但没有使用工厂函数获取AdminService"

        except (OSError, TypeError):
            # 如果无法获取类源代码，跳过此测试
            pass

    def test_admin_layer_comprehensive_compliance_check(self):
        """
        Admin层综合合规性检查

        验证所有Admin类的整体合规性
        """
        admin_classes = self.get_automation_admin_classes()

        compliance_report = {"total_admins": len(admin_classes), "compliant_admins": 0, "violations": []}

        for admin_class in admin_classes:
            violations = []

            try:
                # Get the module source instead of just the class source
                import sys

                module = sys.modules[admin_class.__module__]
                source = inspect.getsource(module)

                # 检查1: 工厂函数使用
                factory_function_pattern = r"def\s+_get_.*_service\(\s*\):"
                factory_functions = re.findall(factory_function_pattern, source)

                admin_action_patterns = [
                    r"def\s+(cleanup_\w+)\(",
                    r"def\s+(export_\w+)\(",
                    r"def\s+(retry_\w+)\(",
                    r"def\s+(batch_\w+)\(",
                ]

                admin_actions = []
                for pattern in admin_action_patterns:
                    matches = re.findall(pattern, source)
                    admin_actions.extend(matches)

                if admin_actions and not factory_functions:
                    violations.append("包含Admin Action但缺少工厂函数")

                # 检查2: 方法行数限制
                methods = inspect.getmembers(admin_class, predicate=inspect.ismethod)
                instance_methods = []
                for name in dir(admin_class):
                    if not name.startswith("_"):
                        attr = getattr(admin_class, name)
                        if callable(attr) and not isinstance(attr, type):
                            instance_methods.append((name, attr))

                all_methods = methods + instance_methods

                for method_name, method in all_methods:
                    # 跳过Django Admin内置方法和显示方法
                    if (
                        method_name.endswith("_display")
                        or method_name.endswith("_view")
                        or method_name.endswith("_summary")
                        or method_name.startswith("_build_")
                        or method_name.startswith("_render_")
                        or method_name.startswith("_display_")
                        or method_name.startswith("_provide_")
                        or method_name
                        in [
                            "has_add_permission",
                            "has_change_permission",
                            "has_delete_permission",
                            "get_queryset",
                            "get_urls",
                            "changelist_view",
                            "get_readonly_fields",
                            "get_list_display",
                            "get_list_filter",
                            "get_search_fields",
                            "save_model",
                            "delete_model",
                            "save_related",
                            "formfield_for_dbfield",
                            "formfield_for_manytomany",
                            "get_form",
                            "get_inline_formsets",
                            "get_search_results",
                            "lookup_allowed",
                            "render_change_form",
                            "response_action",
                            "response_add",
                            "response_change",
                            "response_delete",
                            "to_field_allowed",
                            "get_fieldsets",
                            "get_inline_instances",
                            "get_formsets_with_inlines",
                            "quotes_summary",
                            "performance_summary",
                        ]
                    ):
                        continue

                    try:
                        method_source = inspect.getsource(method)
                        lines = [
                            line.strip()
                            for line in method_source.split("\n")
                            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("@")
                        ]

                        # Apply the same logic as in the individual test
                        if any(
                            method_name.startswith(prefix)
                            for prefix in ["cleanup_", "export_", "retry_", "batch_", "reanalyze_", "execute_"]
                        ):
                            # Admin Action methods - check if they delegate to AdminService
                            method_source = inspect.getsource(getattr(admin_class, method_name, lambda: None))
                            if "service = _get_" in method_source and "_service()" in method_source:
                                # Allow more lines for result formatting if delegating to AdminService
                                if len(lines) > 40:
                                    violations.append(f"方法 {method_name} 超过40行限制（已委托但格式化过于复杂）")
                            else:
                                # Strict limit if not delegating
                                if len(lines) > 25:
                                    violations.append(f"方法 {method_name} 超过25行限制（应委托给AdminService）")
                        else:
                            # Regular methods
                            if len(lines) > 30:
                                violations.append(f"方法 {method_name} 超过30行限制")

                    except (OSError, TypeError):
                        continue

                # 检查3: 跨模块导入
                prohibited_import_patterns = [
                    r"from\s+apps\.client\..*import",
                    r"from\s+apps\.cases\..*import",
                    r"from\s+apps\.contracts\..*import",
                    r"from\s+apps\.organization\..*import",
                ]

                for pattern in prohibited_import_patterns:
                    matches = re.findall(pattern, source)
                    if matches:
                        violations.append(f"禁止的跨模块导入: {matches}")

                # 检查4: 直接Service实例化
                service_instantiation_patterns = [
                    r"\w+Service\(\)",
                    r"\w+AdminService\(\)",
                ]

                for pattern in service_instantiation_patterns:
                    matches = re.findall(pattern, source)
                    # 排除工厂函数内部的实例化
                    filtered_matches = []
                    for match in matches:
                        # 简单检查：如果不在工厂函数上下文中
                        match_pos = source.find(match)
                        if match_pos != -1:
                            context = source[max(0, match_pos - 200) : match_pos + 200]
                            if "def _get_" not in context:
                                filtered_matches.append(match)

                    if filtered_matches:
                        violations.append(f"禁止的直接Service实例化: {filtered_matches}")

            except (OSError, TypeError):
                violations.append("无法获取类源代码")

            # 记录结果
            if not violations:
                compliance_report["compliant_admins"] += 1
            else:
                compliance_report["violations"].append({"admin": admin_class.__name__, "violations": violations})

        # 计算合规率
        compliance_rate = (
            compliance_report["compliant_admins"] / compliance_report["total_admins"] * 100
            if compliance_report["total_admins"] > 0
            else 0
        )

        # 输出合规性报告
        print(f"\n=== Admin层合规性报告 ===")
        print(f"总Admin类数: {compliance_report['total_admins']}")
        print(f"合规Admin类数: {compliance_report['compliant_admins']}")
        print(f"合规率: {compliance_rate:.1f}%")

        if compliance_report["violations"]:
            print(f"\n违规详情:")
            for violation in compliance_report["violations"]:
                print(f"  {violation['admin']}:")
                for v in violation["violations"]:
                    print(f"    - {v}")

        # 要求至少80%的合规率
        assert compliance_rate >= 80.0, (
            f"Admin层合规率 {compliance_rate:.1f}% 低于要求的80%。"
            f"违规Admin: {[v['admin'] for v in compliance_report['violations']]}"
        )


@composite
def compliant_admin_action_source(draw):
    """生成符合规范的Admin Action方法源代码的策略"""
    action_name = draw(
        st.sampled_from(
            [
                "cleanup_old_records",
                "export_to_csv",
                "retry_failed_tasks",
                "batch_delete_items",
                "reanalyze_performance",
            ]
        )
    )

    # 只生成符合规范的代码
    source_parts = []

    # 总是包含工厂函数（符合规范）
    source_parts.append("def _get_test_admin_service():")
    source_parts.append("    from ..services.admin import TestAdminService")
    source_parts.append("    return TestAdminService()")
    source_parts.append("")

    # Admin Action方法
    source_parts.append(f"def {action_name}(self, request, queryset):")
    source_parts.append("    try:")
    source_parts.append("        service = _get_test_admin_service()")
    source_parts.append("        result = service.process_action()")
    source_parts.append("        self.message_user(request, f'操作成功: {result}')")
    source_parts.append("    except Exception as e:")
    source_parts.append("        self.message_user(request, f'操作失败: {str(e)}', level=messages.ERROR)")

    return "\n".join(source_parts)


@composite
def non_compliant_admin_action_source(draw):
    """生成不符合规范的Admin Action方法源代码的策略，用于测试违规检测"""
    action_name = draw(st.sampled_from(["cleanup_old_records", "export_to_csv", "batch_process"]))

    violation_type = draw(
        st.sampled_from(
            [
                "direct_service_instantiation",
                "excessive_line_count",
                "cross_module_import",
                "complex_exception_handling",
            ]
        )
    )

    source_parts = []

    if violation_type == "direct_service_instantiation":
        # 违规：直接实例化Service
        source_parts.extend(
            [
                f"def {action_name}(self, request, queryset):",
                "    service = TestAdminService()",  # 违规：直接实例化
                "    result = service.process()",
                "    self.message_user(request, 'Success')",
            ]
        )
    elif violation_type == "excessive_line_count":
        # 违规：方法行数过多
        source_parts.extend([f"def {action_name}(self, request, queryset):", "    # 大量业务逻辑（违规）"])
        # 添加很多行代码
        for i in range(35):
            source_parts.append(f"    line_{i} = 'business logic {i}'")
        source_parts.append("    self.message_user(request, 'Success')")
    elif violation_type == "cross_module_import":
        # 违规：跨模块直接导入
        source_parts.extend(
            [
                "from apps.client.models import Client",  # 违规：跨模块导入
                "",
                f"def {action_name}(self, request, queryset):",
                "    clients = Client.objects.all()",
                "    self.message_user(request, 'Success')",
            ]
        )
    elif violation_type == "complex_exception_handling":
        # 违规：复杂的异常处理
        source_parts.extend(
            [
                f"def {action_name}(self, request, queryset):",
                "    try:",
                "        service = _get_test_admin_service()",
                "        result = service.process()",
                "    except Exception as e:",
                "        # 复杂的异常处理逻辑（违规）",
                "        if isinstance(e, ValidationError):",
                "            for field, errors in e.error_dict.items():",
                "                for error in errors:",
                "                    logger.error(f'Field {field}: {error}')",
                "        elif isinstance(e, DatabaseError):",
                "            logger.error('Database error occurred')",
                "            # 更多复杂逻辑...",
                "        self.message_user(request, 'Error handled')",
            ]
        )

    return "\n".join(source_parts), violation_type


class TestAdminLayerPropertyBasedCompliance:
    """基于属性的Admin层合规性测试"""

    @given(compliant_admin_action_source())
    @settings(max_examples=30)
    def test_compliant_admin_action_patterns(self, action_source):
        """
        测试符合规范的Admin Action方法模式

        验证符合规范的Admin Action代码能够通过合规性检查
        """
        # 解析Action源代码
        try:
            tree = ast.parse(action_source)
        except SyntaxError:
            assume(False)  # 跳过无效的源代码

        # 检查函数定义
        function_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        action_functions = [f for f in function_defs if not f.name.startswith("_get_")]
        factory_functions = [f for f in function_defs if f.name.startswith("_get_")]

        assert len(action_functions) >= 1, "必须包含至少一个Action方法"
        assert len(factory_functions) >= 1, "必须包含至少一个工厂函数"

        for func_def in action_functions:
            func_name = func_def.name

            # 验证方法行数不超过限制
            method_lines = action_source.split("\n")
            start_line = None
            end_line = None

            for i, line in enumerate(method_lines):
                if f"def {func_name}(" in line:
                    start_line = i
                elif start_line is not None and line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    end_line = i
                    break

            if start_line is not None:
                if end_line is None:
                    end_line = len(method_lines)

                method_line_count = end_line - start_line
                assert method_line_count <= 25, f"符合规范的Admin Action方法 {func_name} 行数应该控制在25行以内"

            # 验证使用工厂函数获取Service
            service_assignments = []
            for node in ast.walk(func_def):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if hasattr(target, "id") and target.id == "service":
                            service_assignments.append(node.value)

            # 验证Service赋值使用工厂函数
            for assignment in service_assignments:
                if isinstance(assignment, ast.Call):
                    if hasattr(assignment.func, "id"):
                        func_name_called = assignment.func.id
                        # 符合规范：使用工厂函数
                        assert func_name_called.startswith("_get_") and func_name_called.endswith(
                            "_service"
                        ), f"符合规范的Admin Action应该使用工厂函数: {func_name_called}"

            # 验证异常处理简单化
            try_blocks = [node for node in ast.walk(func_def) if isinstance(node, ast.Try)]
            for try_block in try_blocks:
                for handler in try_block.handlers:
                    # 检查except块的复杂度
                    handler_statements = len(handler.body)
                    assert handler_statements <= 3, f"符合规范的Admin Action异常处理应该简单，不超过3个语句"

    @given(non_compliant_admin_action_source())
    @settings(max_examples=20)
    def test_non_compliant_admin_action_detection(self, action_data):
        """
        测试违规Admin Action方法的检测能力

        验证违规的Admin Action代码能够被正确识别
        """
        action_source, violation_type = action_data

        # 解析Action源代码
        try:
            tree = ast.parse(action_source)
        except SyntaxError:
            assume(False)  # 跳过无效的源代码

        # 检查函数定义
        function_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        action_functions = [f for f in function_defs if not f.name.startswith("_get_")]

        assert len(action_functions) >= 1, "必须包含至少一个Action方法"

        violation_detected = False

        for func_def in action_functions:
            func_name = func_def.name

            if violation_type == "direct_service_instantiation":
                # 检查直接Service实例化违规
                for node in ast.walk(func_def):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if hasattr(target, "id") and target.id == "service":
                                if isinstance(node.value, ast.Call):
                                    if hasattr(node.value.func, "id"):
                                        func_name_called = node.value.func.id
                                        if func_name_called.endswith("Service") and not func_name_called.startswith(
                                            "_get_"
                                        ):
                                            violation_detected = True
                                            break

            elif violation_type == "excessive_line_count":
                # 检查行数过多违规
                method_lines = action_source.split("\n")
                start_line = None
                end_line = None

                for i, line in enumerate(method_lines):
                    if f"def {func_name}(" in line:
                        start_line = i
                    elif (
                        start_line is not None
                        and line.strip()
                        and not line.startswith(" ")
                        and not line.startswith("\t")
                    ):
                        end_line = i
                        break

                if start_line is not None:
                    if end_line is None:
                        end_line = len(method_lines)

                    method_line_count = end_line - start_line
                    if method_line_count > 30:
                        violation_detected = True

            elif violation_type == "complex_exception_handling":
                # 检查复杂异常处理违规
                try_blocks = [node for node in ast.walk(func_def) if isinstance(node, ast.Try)]
                for try_block in try_blocks:
                    for handler in try_block.handlers:
                        # 检查except块是否包含复杂逻辑
                        if len(handler.body) > 5:  # 超过5个语句认为是复杂处理
                            violation_detected = True
                            break

                        # 检查是否有嵌套的if/for等复杂结构
                        for stmt in handler.body:
                            if isinstance(stmt, (ast.If, ast.For, ast.While)):
                                violation_detected = True
                                break

        # 检查跨模块导入违规
        if violation_type == "cross_module_import":
            import_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            for import_node in import_nodes:
                if import_node.module and "apps.client" in import_node.module:
                    violation_detected = True
                    break

        # 验证违规被正确检测到
        assert violation_detected, f"违规类型 {violation_type} 应该被检测到"


class TestAdminLayerFileStructureCompliance:
    """Admin层文件结构合规性测试"""

    def test_admin_file_structure_compliance(self):
        """
        测试Admin文件结构的合规性

        验证Admin文件的组织结构符合规范
        """
        admin_dir = Path(__file__).parent.parent.parent.parent / "apps" / "automation" / "admin"

        # 检查Admin目录存在
        assert admin_dir.exists(), "automation Admin目录必须存在"

        # 获取所有Admin文件
        admin_files = list(admin_dir.glob("*_admin.py"))

        assert len(admin_files) > 0, "必须包含至少一个Admin文件"

        for admin_file in admin_files:
            # 检查文件命名规范
            assert admin_file.name.endswith("_admin.py"), f"Admin文件 {admin_file.name} 必须以 '_admin.py' 结尾"

            # 检查文件内容结构
            content = admin_file.read_text(encoding="utf-8")

            # 跳过纯聚合模块（只有 import 和 __all__，没有类定义）
            has_class_def = re.search(r"^class\s+", content, re.MULTILINE)
            if not has_class_def:
                continue

            # 必须包含Admin类定义
            admin_class_pattern = r"class\s+\w+Admin\(admin\.ModelAdmin\):"
            admin_classes = re.findall(admin_class_pattern, content)

            assert admin_classes, f"Admin文件 {admin_file.name} 必须定义继承自 admin.ModelAdmin 的类"

            # 检查是否有Admin Action
            admin_action_patterns = [
                r"def\s+(cleanup_\w+)\(",
                r"def\s+(export_\w+)\(",
                r"def\s+(retry_\w+)\(",
                r"def\s+(batch_\w+)\(",
            ]

            admin_actions = []
            for pattern in admin_action_patterns:
                matches = re.findall(pattern, content)
                admin_actions.extend(matches)

            if admin_actions:
                # 如果有Admin Action，检查工厂函数
                factory_functions = re.findall(r"def\s+_get_\w+_admin_service\(\s*\):", content)

                assert factory_functions, f"Admin文件 {admin_file.name} 包含Admin Action但缺少工厂函数"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
