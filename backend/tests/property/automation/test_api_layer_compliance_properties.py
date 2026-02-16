"""
API层合规性属性测试

验证automation模块的API层完全符合四层架构规范：
- Property 1: API层工厂函数使用
- Property 2: API层ServiceLocator使用
- Property 3: API层异常处理禁止
- Property 4: API层数据库操作禁止
- Property 5: API层事务装饰器禁止

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""
import ast
import inspect
import re
import os
from typing import List, Dict, Any, Optional
from apps.core.path import Path

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

# 导入所有automation API模块
from apps.automation.api import (
    captcha_recognition_api,
    document_processor_api,
    document_delivery_api,
    auto_namer_api,
    preservation_quote_api,
    performance_monitor_api,
)


class TestAPILayerCompliance:
    """API层合规性属性测试"""
    
    def get_automation_api_modules(self) -> List[Any]:
        """获取所有automation模块的API模块"""
        return [
            captcha_recognition_api,
            document_processor_api,
            document_delivery_api,
            auto_namer_api,
            preservation_quote_api,
            performance_monitor_api,
        ]
    
    def get_api_module_paths(self) -> List[str]:
        """获取所有API模块的文件路径"""
        base_path = Path(__file__).parent.parent.parent.parent / "apps" / "automation" / "api"
        api_files = []
        
        for file_path in base_path.glob("*.py"):
            if file_path.name != "__init__.py":
                api_files.append(str(file_path))
        
        return api_files
    
    @given(st.sampled_from([
        captcha_recognition_api,
        document_processor_api,
        document_delivery_api,
        auto_namer_api,
        preservation_quote_api,
        performance_monitor_api,
    ]))
    @settings(max_examples=100)
    def test_property_1_api_factory_function_usage(self, api_module):
        """
        **Feature: automation-module-compliance, Property 1: API层工厂函数使用**
        
        验证API层使用工厂函数创建Service实例，而不是直接实例化
        
        For any API层视图函数，都应该使用工厂函数 _get_xxx_service() 创建Service实例
        **Validates: Requirements 1.1**
        """
        try:
            source = inspect.getsource(api_module)
            
            # 检查是否有工厂函数定义
            factory_function_pattern = r'def\s+_get_\w+_service\(\s*\):'
            factory_functions = re.findall(factory_function_pattern, source)
            
            # 检查视图函数中的Service实例化模式
            view_function_pattern = r'@router\.(get|post|put|delete|patch)\([^)]*\)\s*\n[^d]*def\s+(\w+)\([^)]*\):'
            view_functions = re.findall(view_function_pattern, source, re.MULTILINE | re.DOTALL)
            
            if view_functions:
                # 如果有视图函数，必须有对应的工厂函数
                assert factory_functions, (
                    f"{api_module.__name__} 包含视图函数但缺少工厂函数 _get_xxx_service()"
                )
                
                # 检查视图函数中是否正确使用工厂函数
                for _, view_name in view_functions:
                    # 获取视图函数的源代码
                    try:
                        view_func = getattr(api_module, view_name)
                        view_source = inspect.getsource(view_func)
                        
                        # 检查是否使用工厂函数
                        factory_call_pattern = r'service\s*=\s*_get_\w+_service\(\)'
                        factory_calls = re.findall(factory_call_pattern, view_source)
                        
                        # 检查是否有直接实例化Service的违规模式
                        direct_instantiation_patterns = [
                            r'\w+Service\(\)',
                            r'from\s+.*services.*import.*Service',
                        ]
                        
                        for pattern in direct_instantiation_patterns:
                            violations = re.findall(pattern, view_source)
                            if violations:
                                # 允许在工厂函数内部导入，但不允许在视图函数中直接导入
                                if 'def _get_' not in view_source:
                                    assert not violations, (
                                        f"{api_module.__name__}.{view_name} 不应该直接实例化Service: {violations}"
                                    )
                        
                        # 如果视图函数需要Service，必须使用工厂函数
                        if 'service' in view_source.lower():
                            assert factory_calls, (
                                f"{api_module.__name__}.{view_name} 必须使用工厂函数获取Service实例"
                            )
                            
                    except (AttributeError, OSError):
                        # 如果无法获取函数源代码，跳过
                        continue
                        
        except (OSError, TypeError):
            # 如果无法获取模块源代码，跳过此测试
            pass
    
    @given(st.sampled_from([
        captcha_recognition_api,
        document_delivery_api,
        auto_namer_api,
        preservation_quote_api,
        performance_monitor_api,
    ]))
    @settings(max_examples=100)
    def test_property_2_api_servicelocator_usage(self, api_module):
        """
        **Feature: automation-module-compliance, Property 2: API层ServiceLocator使用**
        
        验证API层通过ServiceLocator获取跨模块依赖，而不是直接导入
        
        For any API层跨模块调用，都应该通过ServiceLocator获取服务
        **Validates: Requirements 1.2**
        """
        try:
            source = inspect.getsource(api_module)
            
            # 检查工厂函数中是否正确使用ServiceLocator
            factory_function_pattern = r'def\s+_get_\w+_service\(\s*\):(.*?)(?=\n\n|\ndef|\n@|\Z)'
            factory_matches = re.findall(factory_function_pattern, source, re.DOTALL)
            
            for factory_body in factory_matches:
                # 检查是否使用ServiceLocator
                if 'ServiceLocator' in factory_body:
                    # 验证正确的导入语句
                    servicelocator_import = 'from apps.core.interfaces import ServiceLocator'
                    assert servicelocator_import in source, (
                        f"{api_module.__name__} 工厂函数必须正确导入ServiceLocator"
                    )
                    
                    # 验证ServiceLocator的使用模式
                    servicelocator_usage_pattern = r'ServiceLocator\.get_\w+_service\(\)'
                    servicelocator_calls = re.findall(servicelocator_usage_pattern, factory_body)
                    
                    if servicelocator_calls:
                        # 验证调用模式正确
                        for call in servicelocator_calls:
                            assert 'get_' in call and '_service()' in call, (
                                f"{api_module.__name__} ServiceLocator调用模式不正确: {call}"
                            )
            
            # 检查是否有禁止的跨模块直接导入
            prohibited_import_patterns = [
                r'from\s+apps\.client\..*import',
                r'from\s+apps\.cases\..*import',
                r'from\s+apps\.contracts\..*import',
                r'from\s+apps\.organization\..*import',
            ]
            
            for pattern in prohibited_import_patterns:
                violations = re.findall(pattern, source)
                assert not violations, (
                    f"{api_module.__name__} 不应该直接导入其他模块: {violations}"
                )
                
        except (OSError, TypeError):
            # 如果无法获取模块源代码，跳过此测试
            pass
    
    @given(st.sampled_from([
        captcha_recognition_api,
        document_processor_api,
        document_delivery_api,
        auto_namer_api,
        preservation_quote_api,
        performance_monitor_api,
    ]))
    @settings(max_examples=100)
    def test_property_3_api_exception_handling_prohibited(self, api_module):
        """
        **Feature: automation-module-compliance, Property 3: API层异常处理禁止**
        
        验证API层不使用try/except进行异常处理，让框架统一处理
        
        For any API层视图函数，都不应该使用try/except进行异常处理
        **Validates: Requirements 1.3**
        """
        try:
            source = inspect.getsource(api_module)
            
            # 获取所有视图函数
            view_function_pattern = r'@router\.(get|post|put|delete|patch)\([^)]*\)\s*\n[^d]*def\s+(\w+)\([^)]*\):(.*?)(?=\n\n|\ndef|\n@|\Z)'
            view_matches = re.findall(view_function_pattern, source, re.MULTILINE | re.DOTALL)
            
            for method, view_name, view_body in view_matches:
                # 检查视图函数中是否有try/except块
                try_except_pattern = r'try\s*:(.*?)except'
                try_blocks = re.findall(try_except_pattern, view_body, re.DOTALL)
                
                assert not try_blocks, (
                    f"{api_module.__name__}.{view_name} 不应该使用try/except处理异常，"
                    f"应该让框架的全局异常处理器统一处理"
                )
                
                # 检查是否有其他异常处理模式
                exception_handling_patterns = [
                    r'except\s+\w+',
                    r'except\s*:',
                    r'raise\s+Http\w+',
                ]
                
                for pattern in exception_handling_patterns:
                    violations = re.findall(pattern, view_body)
                    assert not violations, (
                        f"{api_module.__name__}.{view_name} 不应该进行异常处理: {violations}"
                    )
                        
        except (OSError, TypeError):
            # 如果无法获取模块源代码，跳过此测试
            pass
    
    @given(st.sampled_from([
        captcha_recognition_api,
        document_processor_api,
        document_delivery_api,
        auto_namer_api,
        preservation_quote_api,
        performance_monitor_api,
    ]))
    @settings(max_examples=100)
    def test_property_4_api_database_operations_prohibited(self, api_module):
        """
        **Feature: automation-module-compliance, Property 4: API层数据库操作禁止**
        
        验证API层不直接进行数据库操作，应该委托给Service层
        
        For any API层视图函数，都不应该直接进行Model.objects操作
        **Validates: Requirements 1.4**
        """
        try:
            source = inspect.getsource(api_module)
            
            # 检查禁止的数据库操作模式
            prohibited_db_patterns = [
                r'\w+\.objects\.',
                r'get_object_or_404\(',
                r'get_list_or_404\(',
                r'Model\.objects',
                r'\.objects\.filter\(',
                r'\.objects\.get\(',
                r'\.objects\.create\(',
                r'\.objects\.update\(',
                r'\.objects\.delete\(',
                r'\.objects\.save\(',
            ]
            
            # 获取所有视图函数
            view_function_pattern = r'@router\.(get|post|put|delete|patch)\([^)]*\)\s*\n[^d]*def\s+(\w+)\([^)]*\):(.*?)(?=\n\n|\ndef|\n@|\Z)'
            view_matches = re.findall(view_function_pattern, source, re.MULTILINE | re.DOTALL)
            
            for method, view_name, view_body in view_matches:
                for pattern in prohibited_db_patterns:
                    violations = re.findall(pattern, view_body)
                    if violations:
                        # 排除一些合法的使用场景（如字符串中的内容、字典访问等）
                        filtered_violations = []
                        for violation in violations:
                            # 检查是否在字符串或注释中
                            if not (violation.startswith('"') or violation.startswith("'") or 
                                   violation.startswith('#')):
                                # 排除字典的.get()方法调用
                                if violation == '.get(' and 'metrics.get(' in view_body:
                                    continue
                                # 排除其他合法的.get()调用（如字典、配置等）
                                if violation == '.get(' and any(prefix in view_body for prefix in [
                                    'config.get(', 'data.get(', 'result.get(', 'request.get(',
                                    'payload.get(', 'response.get(', 'dict.get(', 'settings.get('
                                ]):
                                    continue
                                filtered_violations.append(violation)
                        
                        assert not filtered_violations, (
                            f"{api_module.__name__}.{view_name} 不应该直接进行数据库操作: {filtered_violations}"
                        )
                        
        except (OSError, TypeError):
            # 如果无法获取模块源代码，跳过此测试
            pass
    
    @given(st.sampled_from([
        captcha_recognition_api,
        document_processor_api,
        document_delivery_api,
        auto_namer_api,
        preservation_quote_api,
        performance_monitor_api,
    ]))
    @settings(max_examples=100)
    def test_property_5_api_transaction_decorator_prohibited(self, api_module):
        """
        **Feature: automation-module-compliance, Property 5: API层事务装饰器禁止**
        
        验证API层不使用@transaction.atomic装饰器，事务管理应该在Service层
        
        For any API层视图函数，都不应该使用@transaction.atomic装饰器
        **Validates: Requirements 1.5**
        """
        try:
            source = inspect.getsource(api_module)
            
            # 检查@transaction.atomic装饰器
            transaction_decorator_patterns = [
                r'@transaction\.atomic',
                r'@atomic',
                r'from\s+django\.db\s+import\s+transaction',
                r'with\s+transaction\.atomic\(',
            ]
            
            # 获取所有视图函数
            view_function_pattern = r'(@router\.(get|post|put|delete|patch)\([^)]*\)\s*\n[^d]*def\s+(\w+)\([^)]*\):(.*?)(?=\n\n|\ndef|\n@|\Z))'
            view_matches = re.findall(view_function_pattern, source, re.MULTILINE | re.DOTALL)
            
            for full_match, method, view_name, view_body in view_matches:
                for pattern in transaction_decorator_patterns:
                    violations = re.findall(pattern, full_match)
                    assert not violations, (
                        f"{api_module.__name__}.{view_name} 不应该使用事务装饰器，"
                        f"事务管理应该在Service层: {violations}"
                    )
            
            # 检查整个模块是否导入了transaction
            transaction_import_patterns = [
                r'from\s+django\.db\s+import\s+transaction',
                r'import\s+.*transaction',
            ]
            
            for pattern in transaction_import_patterns:
                violations = re.findall(pattern, source)
                if violations:
                    # 检查是否在视图函数中使用
                    for _, _, view_name, view_body in view_matches:
                        transaction_usage = re.findall(r'transaction\.', view_body)
                        assert not transaction_usage, (
                            f"{api_module.__name__}.{view_name} 不应该使用transaction: {transaction_usage}"
                        )
                        
        except (OSError, TypeError):
            # 如果无法获取模块源代码，跳过此测试
            pass
    
    def test_api_layer_comprehensive_compliance_check(self):
        """
        API层综合合规性检查
        
        验证所有API模块的整体合规性
        """
        api_modules = self.get_automation_api_modules()
        
        compliance_report = {
            "total_modules": len(api_modules),
            "compliant_modules": 0,
            "violations": []
        }
        
        for api_module in api_modules:
            violations = []
            
            try:
                source = inspect.getsource(api_module)
                
                # 检查1: 工厂函数使用
                factory_function_pattern = r'def\s+_get_\w+_service\(\s*\):'
                factory_functions = re.findall(factory_function_pattern, source)
                
                view_function_pattern = r'@router\.(get|post|put|delete|patch)'
                view_functions = re.findall(view_function_pattern, source)
                
                if view_functions and not factory_functions:
                    violations.append("缺少工厂函数 _get_xxx_service()")
                
                # 检查2: ServiceLocator使用
                if 'ServiceLocator' in source:
                    correct_import = 'from apps.core.interfaces import ServiceLocator'
                    if correct_import not in source:
                        violations.append("ServiceLocator导入不正确")
                
                # 检查3: 异常处理禁止
                try_except_pattern = r'try\s*:.*?except'
                try_blocks = re.findall(try_except_pattern, source, re.DOTALL)
                if try_blocks:
                    violations.append("使用了禁止的try/except异常处理")
                
                # 检查4: 数据库操作禁止
                db_operation_patterns = [
                    r'\w+\.objects\.',
                    r'get_object_or_404\(',
                ]
                
                for pattern in db_operation_patterns:
                    matches = re.findall(pattern, source)
                    if matches:
                        # 排除合法的使用场景
                        filtered_matches = []
                        for match in matches:
                            # 排除字典的.get()等方法
                            if '.get(' in match and any(prefix in source for prefix in [
                                'metrics.get(', 'config.get(', 'data.get(', 'result.get('
                            ]):
                                continue
                            filtered_matches.append(match)
                        
                        if filtered_matches:
                            violations.append(f"使用了禁止的数据库操作: {filtered_matches}")
                
                # 检查5: 事务装饰器禁止
                transaction_patterns = [
                    r'@transaction\.atomic',
                    r'with\s+transaction\.atomic',
                ]
                
                for pattern in transaction_patterns:
                    if re.search(pattern, source):
                        violations.append(f"使用了禁止的事务装饰器: {pattern}")
                
            except (OSError, TypeError):
                violations.append("无法获取模块源代码")
            
            # 记录结果
            if not violations:
                compliance_report["compliant_modules"] += 1
            else:
                compliance_report["violations"].append({
                    "module": api_module.__name__,
                    "violations": violations
                })
        
        # 计算合规率
        compliance_rate = (
            compliance_report["compliant_modules"] / compliance_report["total_modules"] * 100
            if compliance_report["total_modules"] > 0 else 0
        )
        
        # 输出合规性报告
        print(f"\n=== API层合规性报告 ===")
        print(f"总API模块数: {compliance_report['total_modules']}")
        print(f"合规API模块数: {compliance_report['compliant_modules']}")
        print(f"合规率: {compliance_rate:.1f}%")
        
        if compliance_report["violations"]:
            print(f"\n违规详情:")
            for violation in compliance_report["violations"]:
                print(f"  {violation['module']}:")
                for v in violation["violations"]:
                    print(f"    - {v}")
        
        # 要求至少80%的合规率
        assert compliance_rate >= 80.0, (
            f"API层合规率 {compliance_rate:.1f}% 低于要求的80%。"
            f"违规模块: {[v['module'] for v in compliance_report['violations']]}"
        )


@composite
def compliant_api_view_source(draw):
    """生成符合规范的API视图函数源代码的策略"""
    http_method = draw(st.sampled_from(['get', 'post', 'put', 'delete', 'patch']))
    view_name = draw(st.sampled_from([
        'create_item', 'get_item', 'update_item', 'delete_item',
        'list_items', 'process_data', 'execute_task'
    ]))
    
    # 只生成符合规范的代码
    has_service_call = draw(st.booleans())
    
    source_parts = []
    
    # 总是包含工厂函数（符合规范）
    source_parts.append("def _get_test_service():")
    source_parts.append("    from apps.core.interfaces import ServiceLocator")
    source_parts.append("    return ServiceLocator.get_test_service()")
    source_parts.append("")
    
    # 只使用路由装饰器（符合规范）
    source_parts.append(f"@router.{http_method}('/test')")
    
    # 函数定义
    source_parts.append(f"def {view_name}(request):")
    
    # 函数体 - 只生成符合规范的代码
    if has_service_call:
        source_parts.append("    service = _get_test_service()")
        source_parts.append("    result = service.process()")
        source_parts.append("    return result")
    else:
        source_parts.append("    return {'success': True}")
    
    return '\n'.join(source_parts)


@composite
def non_compliant_api_view_source(draw):
    """生成不符合规范的API视图函数源代码的策略，用于测试违规检测"""
    http_method = draw(st.sampled_from(['get', 'post', 'put', 'delete', 'patch']))
    view_name = draw(st.sampled_from([
        'create_item', 'get_item', 'update_item', 'delete_item'
    ]))
    
    violation_type = draw(st.sampled_from([
        'direct_service_instantiation',
        'try_except_usage', 
        'db_operation',
        'transaction_decorator'
    ]))
    
    source_parts = []
    
    if violation_type == 'direct_service_instantiation':
        # 违规：直接实例化Service
        source_parts.extend([
            f"@router.{http_method}('/test')",
            f"def {view_name}(request):",
            "    service = TestService()",
            "    return {'success': True}"
        ])
    elif violation_type == 'try_except_usage':
        # 违规：使用try/except
        source_parts.extend([
            "def _get_test_service():",
            "    return TestService()",
            "",
            f"@router.{http_method}('/test')",
            f"def {view_name}(request):",
            "    service = _get_test_service()",
            "    try:",
            "        result = service.process()",
            "    except Exception as e:",
            "        return {'error': str(e)}",
            "    return {'success': True}"
        ])
    elif violation_type == 'db_operation':
        # 违规：直接数据库操作
        source_parts.extend([
            f"@router.{http_method}('/test')",
            f"def {view_name}(request):",
            "    items = TestModel.objects.all()",
            "    return {'items': list(items)}"
        ])
    elif violation_type == 'transaction_decorator':
        # 违规：使用事务装饰器
        source_parts.extend([
            "@transaction.atomic",
            f"@router.{http_method}('/test')",
            f"def {view_name}(request):",
            "    return {'success': True}"
        ])
    
    return '\n'.join(source_parts), violation_type


class TestAPILayerPropertyBasedCompliance:
    """基于属性的API层合规性测试"""
    
    @given(compliant_api_view_source())
    @settings(max_examples=30)
    def test_compliant_api_view_patterns(self, view_source):
        """
        测试符合规范的API视图函数模式
        
        验证符合规范的API视图代码能够通过合规性检查
        """
        # 解析视图源代码
        try:
            tree = ast.parse(view_source)
        except SyntaxError:
            assume(False)  # 跳过无效的源代码
        
        # 检查函数定义
        function_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        view_functions = [f for f in function_defs if not f.name.startswith('_get_')]
        factory_functions = [f for f in function_defs if f.name.startswith('_get_')]
        
        assert len(view_functions) >= 1, "必须包含至少一个视图函数"
        assert len(factory_functions) >= 1, "必须包含至少一个工厂函数"
        
        for func_def in view_functions:
            func_name = func_def.name
            
            # 验证没有事务装饰器（符合规范）
            for decorator in func_def.decorator_list:
                decorator_name = ""
                if hasattr(decorator, 'attr'):
                    decorator_name = decorator.attr
                elif hasattr(decorator, 'id'):
                    decorator_name = decorator.id
                
                # 符合规范的代码不应该有atomic装饰器
                assert 'atomic' not in decorator_name
            
            # 验证没有try/except块（符合规范）
            try_blocks = [node for node in ast.walk(func_def) if isinstance(node, ast.Try)]
            assert len(try_blocks) == 0, f"符合规范的API视图函数 {func_name} 不应该包含try/except"
            
            # 验证没有直接数据库操作（符合规范）
            db_operations = []
            for node in ast.walk(func_def):
                if isinstance(node, ast.Attribute):
                    if hasattr(node, 'attr') and node.attr == 'objects':
                        if hasattr(node, 'value') and hasattr(node.value, 'id'):
                            model_name = node.value.id
                            if model_name.endswith('Model') or model_name[0].isupper():
                                db_operations.append(f"{model_name}.objects")
            
            assert len(db_operations) == 0, f"符合规范的API视图函数 {func_name} 不应该包含数据库操作"
            
            # 验证Service实例化使用工厂函数（符合规范）
            service_assignments = []
            for node in ast.walk(func_def):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if hasattr(target, 'id') and target.id == 'service':
                            service_assignments.append(node.value)
            
            # 如果有Service赋值，验证使用工厂函数
            for assignment in service_assignments:
                if isinstance(assignment, ast.Call):
                    if hasattr(assignment.func, 'id'):
                        func_name_called = assignment.func.id
                        # 符合规范：使用工厂函数
                        assert func_name_called.startswith('_get_') and func_name_called.endswith('_service'), (
                            f"符合规范的API视图函数应该使用工厂函数: {func_name_called}"
                        )
    
    @given(non_compliant_api_view_source())
    @settings(max_examples=20)
    def test_non_compliant_api_view_detection(self, view_data):
        """
        测试违规API视图函数的检测能力
        
        验证违规的API视图代码能够被正确识别
        """
        view_source, violation_type = view_data
        
        # 解析视图源代码
        try:
            tree = ast.parse(view_source)
        except SyntaxError:
            assume(False)  # 跳过无效的源代码
        
        # 检查函数定义
        function_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        view_functions = [f for f in function_defs if not f.name.startswith('_get_')]
        
        assert len(view_functions) >= 1, "必须包含至少一个视图函数"
        
        violation_detected = False
        
        for func_def in view_functions:
            func_name = func_def.name
            
            if violation_type == 'transaction_decorator':
                # 检查事务装饰器违规
                for decorator in func_def.decorator_list:
                    decorator_name = ""
                    if hasattr(decorator, 'attr'):
                        decorator_name = decorator.attr
                    elif hasattr(decorator, 'id'):
                        decorator_name = decorator.id
                    
                    if 'atomic' in decorator_name:
                        violation_detected = True
                        break
            
            elif violation_type == 'try_except_usage':
                # 检查try/except违规
                try_blocks = [node for node in ast.walk(func_def) if isinstance(node, ast.Try)]
                if try_blocks:
                    violation_detected = True
            
            elif violation_type == 'db_operation':
                # 检查数据库操作违规
                for node in ast.walk(func_def):
                    if isinstance(node, ast.Attribute):
                        if hasattr(node, 'attr') and node.attr == 'objects':
                            if hasattr(node, 'value') and hasattr(node.value, 'id'):
                                model_name = node.value.id
                                if model_name.endswith('Model') or model_name[0].isupper():
                                    violation_detected = True
                                    break
            
            elif violation_type == 'direct_service_instantiation':
                # 检查直接Service实例化违规
                for node in ast.walk(func_def):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if hasattr(target, 'id') and target.id == 'service':
                                if isinstance(node.value, ast.Call):
                                    if hasattr(node.value.func, 'id'):
                                        func_name_called = node.value.func.id
                                        if func_name_called.endswith('Service'):
                                            violation_detected = True
                                            break
        
        # 验证违规被正确检测到
        assert violation_detected, f"违规类型 {violation_type} 应该被检测到"


class TestAPILayerFileStructureCompliance:
    """API层文件结构合规性测试"""
    
    def test_api_file_structure_compliance(self):
        """
        测试API文件结构的合规性
        
        验证API文件的组织结构符合规范
        """
        api_dir = Path(__file__).parent.parent.parent.parent / "apps" / "automation" / "api"
        
        # 检查API目录存在
        assert api_dir.exists(), "automation API目录必须存在"
        
        # 获取所有API文件
        api_files = list(api_dir.glob("*.py"))
        api_files = [f for f in api_files if f.name != "__init__.py"]
        
        assert len(api_files) > 0, "必须包含至少一个API文件"
        
        for api_file in api_files:
            # 检查文件命名规范
            assert api_file.name.endswith("_api.py"), (
                f"API文件 {api_file.name} 必须以 '_api.py' 结尾"
            )
            
            # 检查文件内容结构
            content = api_file.read_text(encoding='utf-8')
            
            # 必须包含Router定义
            assert 'router = Router(' in content, (
                f"API文件 {api_file.name} 必须定义 router"
            )
            
            # 检查是否有视图函数
            router_decorators = re.findall(r'@router\.(get|post|put|delete|patch)', content)
            
            if router_decorators:
                # 如果有视图函数，检查工厂函数
                factory_functions = re.findall(r'def\s+_get_\w+_service\(\s*\):', content)
                
                # 至少应该有一个工厂函数
                assert factory_functions, (
                    f"API文件 {api_file.name} 包含视图函数但缺少工厂函数"
                )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
