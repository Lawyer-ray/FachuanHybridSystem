# -*- coding: utf-8 -*-
"""
Automation Document/SMS 解耦架构合规性属性测试

验证拆分后的服务文件符合架构规范：
- Property 1: 文件行数限制
- Property 2: 架构合规性
- Property 3: 跨模块调用规范

Requirements: 1.2, 2.2, 3.4, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""
import ast
import inspect
import re
from apps.core.path import Path
from typing import List, Dict, Tuple, Optional, Set

import pytest
from hypothesis import given, strategies as st, assume, settings


def get_backend_path() -> Path:
    """获取 backend 目录路径"""
    return Path(__file__).parent.parent.parent.parent


# ============ 文件行数限制配置 ============

# 文件行数限制配置
FILE_LINE_LIMITS = {
    # Coordinator 文件限制 200 行
    "coordinator": 200,
    # Stage 文件限制 300 行
    "stage": 300,
    # Service 文件限制 500 行
    "service": 500,
    # 默认限制
    "default": 500,
}

# 需要检查的拆分后的文件
DECOUPLED_FILES = {
    # document_delivery 子模块
    "document_delivery/coordinator/document_delivery_coordinator.py": "coordinator",
    "document_delivery/token/document_delivery_token_service.py": "service",
    "document_delivery/api/document_delivery_api_service.py": "service",
    "document_delivery/playwright/document_delivery_playwright_service.py": "service",
    "document_delivery/processor/document_delivery_processor.py": "service",
    # sms 子模块
    "sms/coordinator/court_sms_coordinator.py": "coordinator",
    "sms/stages/sms_parsing_stage.py": "stage",
    "sms/stages/sms_downloading_stage.py": "stage",
    "sms/stages/sms_matching_stage.py": "stage",
    "sms/stages/sms_renaming_stage.py": "stage",
    "sms/stages/sms_notifying_stage.py": "stage",
    "sms/stages/base.py": "stage",
    "sms/submission/sms_submission_service.py": "service",
    "sms/matching/case_matcher.py": "service",
    "sms/matching/document_parser_service.py": "service",
    "sms/matching/party_matching_service.py": "service",
}


def count_file_lines(file_path: Path) -> int:
    """
    统计文件行数（不包括空行和纯注释行）
    
    Args:
        file_path: 文件路径
        
    Returns:
        有效代码行数
    """
    if not file_path.exists():
        return 0
    
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 统计非空行和非纯注释行
        code_lines = 0
        in_multiline_string = False
        
        for line in lines:
            stripped = line.strip()
            
            # 跳过空行
            if not stripped:
                continue
            
            # 处理多行字符串
            if '"""' in stripped or "'''" in stripped:
                count = stripped.count('"""') + stripped.count("'''")
                if count == 1:
                    in_multiline_string = not in_multiline_string
                code_lines += 1
                continue
            
            if in_multiline_string:
                code_lines += 1
                continue
            
            # 跳过纯注释行
            if stripped.startswith('#'):
                continue
            
            code_lines += 1
        
        return code_lines
        
    except Exception:
        return 0


def count_total_lines(file_path: Path) -> int:
    """
    统计文件总行数
    
    Args:
        file_path: 文件路径
        
    Returns:
        总行数
    """
    if not file_path.exists():
        return 0
    
    try:
        content = file_path.read_text(encoding='utf-8')
        return len(content.split('\n'))
    except Exception:
        return 0


class TestFileSizeLimitProperties:
    """
    Property 1: 文件行数限制
    
    *For any* 拆分后的服务文件，其代码行数 SHALL 不超过指定的限制
    （Coordinator 200 行，Stage 300 行，Service 500 行）
    
    **Feature: automation-document-sms-decoupling, Property 1: 文件行数限制**
    **Validates: Requirements 1.2, 2.2, 4.3**
    """
    
    def get_automation_services_path(self) -> Path:
        """获取 automation services 目录路径"""
        return get_backend_path() / "apps" / "automation" / "services"
    
    def get_decoupled_files(self) -> List[Tuple[Path, str, int]]:
        """
        获取所有需要检查的拆分后的文件
        
        Returns:
            (文件路径, 文件类型, 行数限制) 列表
        """
        services_path = self.get_automation_services_path()
        files = []
        
        for relative_path, file_type in DECOUPLED_FILES.items():
            full_path = services_path / relative_path
            limit = FILE_LINE_LIMITS.get(file_type, FILE_LINE_LIMITS["default"])
            files.append((full_path, file_type, limit))
        
        return files
    
    @pytest.mark.property_test
    def test_property_1_file_line_limits(self):
        """
        Property 1: 文件行数限制
        
        *For any* 拆分后的服务文件，其代码行数 SHALL 不超过指定的限制
        
        **Feature: automation-document-sms-decoupling, Property 1: 文件行数限制**
        **Validates: Requirements 1.2, 2.2, 4.3**
        """
        violations = []
        checked_files = 0
        
        for file_path, file_type, limit in self.get_decoupled_files():
            if not file_path.exists():
                # 文件不存在，跳过（可能还未创建）
                continue
            
            checked_files += 1
            total_lines = count_total_lines(file_path)
            
            if total_lines > limit:
                violations.append({
                    "file": file_path.name,
                    "type": file_type,
                    "lines": total_lines,
                    "limit": limit,
                    "excess": total_lines - limit
                })
        
        # 输出检查报告
        print(f"\n=== 文件行数限制检查报告 ===")
        print(f"检查文件数: {checked_files}")
        print(f"违规文件数: {len(violations)}")
        
        if violations:
            print("\n违规详情:")
            for v in violations:
                print(
                    f"  {v['file']} ({v['type']}): "
                    f"{v['lines']} 行 > {v['limit']} 行限制 "
                    f"(超出 {v['excess']} 行)"
                )
        
        assert len(violations) == 0, (
            f"发现 {len(violations)} 个文件超出行数限制:\n" +
            "\n".join(
                f"  {v['file']}: {v['lines']} 行 > {v['limit']} 行"
                for v in violations
            )
        )
    
    @given(st.sampled_from(list(DECOUPLED_FILES.keys())))
    @settings(max_examples=100)
    @pytest.mark.property_test
    def test_property_1_file_line_limits_property_based(self, relative_path: str):
        """
        Property 1: 文件行数限制 (Property-Based)
        
        *For any* 拆分后的服务文件，其代码行数 SHALL 不超过指定的限制
        
        **Feature: automation-document-sms-decoupling, Property 1: 文件行数限制**
        **Validates: Requirements 1.2, 2.2, 4.3**
        """
        services_path = self.get_automation_services_path()
        file_path = services_path / relative_path
        
        # 如果文件不存在，跳过
        assume(file_path.exists())
        
        file_type = DECOUPLED_FILES[relative_path]
        limit = FILE_LINE_LIMITS.get(file_type, FILE_LINE_LIMITS["default"])
        total_lines = count_total_lines(file_path)
        
        assert total_lines <= limit, (
            f"{file_path.name} ({file_type}) 超出行数限制: "
            f"{total_lines} 行 > {limit} 行"
        )



# ============ 架构合规性检查 ============

# 禁止的模式
PROHIBITED_PATTERNS = {
    "staticmethod": r"@staticmethod",
    "direct_model_import": r"from\s+apps\.(client|cases|contracts|organization)\.models\s+import",
}

# 必需的模式
REQUIRED_PATTERNS = {
    "lazy_loading_property": r"@property",
    "service_locator_import": r"from\s+apps\.core\.interfaces\s+import\s+ServiceLocator",
}


def check_file_for_staticmethod(file_path: Path) -> List[Tuple[int, str]]:
    """
    检查文件中是否使用了 @staticmethod 装饰器
    
    Args:
        file_path: 文件路径
        
    Returns:
        (行号, 行内容) 列表
    """
    violations = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 只检测实际的装饰器使用，排除注释中的提及
            if stripped.startswith('@staticmethod'):
                violations.append((i, stripped))
                
    except Exception:
        pass
    
    return violations


def check_file_for_cross_module_model_import(file_path: Path) -> List[Tuple[int, str]]:
    """
    检查文件中是否直接导入了跨模块的 Model
    
    Args:
        file_path: 文件路径
        
    Returns:
        (行号, 行内容) 列表
    """
    violations = []
    
    # 跨模块 Model 导入模式
    cross_module_patterns = [
        r"from\s+apps\.client\.models\s+import",
        r"from\s+apps\.cases\.models\s+import",
        r"from\s+apps\.contracts\.models\s+import",
        r"from\s+apps\.organization\.models\s+import",
    ]
    
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            for pattern in cross_module_patterns:
                if re.search(pattern, line):
                    violations.append((i, line.strip()))
                    break
                    
    except Exception:
        pass
    
    return violations


def check_file_has_lazy_loading(file_path: Path) -> bool:
    """
    检查文件中是否使用了 @property 进行延迟加载
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否使用了延迟加载
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # 检查是否有依赖属性（_xxx_service 或 _xxx_client）
        has_dependencies = bool(
            re.search(r'self\._\w+_service', content) or
            re.search(r'self\._\w+_client', content)
        )
        
        # 如果有依赖，检查是否有 @property
        if has_dependencies:
            return '@property' in content
        
        # 没有依赖，不需要延迟加载
        return True
        
    except Exception:
        return True


def check_file_uses_service_locator_correctly(file_path: Path) -> Tuple[bool, str]:
    """
    检查文件是否正确使用 ServiceLocator 进行跨模块调用
    
    Args:
        file_path: 文件路径
        
    Returns:
        (是否正确, 错误信息)
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # 检查是否导入了 ServiceLocator
        has_service_locator_import = (
            'from apps.core.interfaces import ServiceLocator' in content or
            'from apps.core.interfaces import' in content and 'ServiceLocator' in content
        )
        
        if has_service_locator_import:
            # 验证导入语句正确
            correct_import_patterns = [
                'from apps.core.interfaces import ServiceLocator',
                'from apps.core.interfaces import',  # 可能是多个导入
            ]
            has_correct_import = any(
                pattern in content for pattern in correct_import_patterns
            )
            if not has_correct_import:
                return False, "ServiceLocator 导入语句不正确"
        
        return True, ""
        
    except Exception as e:
        return False, str(e)


def check_constructor_supports_di(file_path: Path) -> List[Tuple[str, str]]:
    """
    检查文件中的类构造函数是否支持依赖注入
    
    Args:
        file_path: 文件路径
        
    Returns:
        (类名, 错误信息) 列表
    """
    violations = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                
                # 跳过接口类和基类
                if class_name.startswith('I') or class_name.startswith('Base'):
                    continue
                
                # 查找 __init__ 方法
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        # 检查参数是否都有默认值
                        args = item.args
                        
                        # 获取非 self 参数
                        non_self_args = [
                            arg for arg in args.args
                            if arg.arg != 'self'
                        ]
                        
                        # 获取默认值数量
                        defaults_count = len(args.defaults)
                        required_count = len(non_self_args) - defaults_count
                        
                        if required_count > 0:
                            violations.append((
                                class_name,
                                f"构造函数有 {required_count} 个必需参数，不支持无参数实例化"
                            ))
                        
    except Exception:
        pass
    
    return violations


class TestArchitectureComplianceProperties:
    """
    Property 2: 架构合规性
    
    *For any* 拆分后的服务文件，SHALL 满足以下条件：
    - 不使用 @staticmethod
    - 通过工厂函数或依赖注入获取依赖
    - 使用 apps.core.exceptions 中定义的异常类
    - 遵循延迟加载模式
    - 不直接导入跨模块的 Model
    
    **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
    **Validates: Requirements 5.1, 5.2, 5.4, 5.5, 5.6**
    """
    
    def get_automation_services_path(self) -> Path:
        """获取 automation services 目录路径"""
        return get_backend_path() / "apps" / "automation" / "services"
    
    def get_all_decoupled_files(self) -> List[Path]:
        """获取所有拆分后的文件路径"""
        services_path = self.get_automation_services_path()
        files = []
        
        for relative_path in DECOUPLED_FILES.keys():
            full_path = services_path / relative_path
            if full_path.exists():
                files.append(full_path)
        
        return files
    
    @pytest.mark.property_test
    def test_property_2_no_staticmethod(self):
        """
        Property 2.1: 不使用 @staticmethod
        
        *For any* 拆分后的服务文件，SHALL 不使用 @staticmethod
        
        **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
        **Validates: Requirements 5.1**
        """
        all_violations = []
        
        for file_path in self.get_all_decoupled_files():
            violations = check_file_for_staticmethod(file_path)
            if violations:
                all_violations.append({
                    "file": file_path.name,
                    "violations": violations
                })
        
        if all_violations:
            error_msg = "发现使用 @staticmethod 的文件:\n"
            for v in all_violations:
                error_msg += f"\n{v['file']}:\n"
                for line_no, line_content in v['violations']:
                    error_msg += f"  行 {line_no}: {line_content}\n"
            
            assert False, error_msg
    
    @pytest.mark.property_test
    def test_property_2_no_cross_module_model_import(self):
        """
        Property 2.2: 不直接导入跨模块的 Model
        
        *For any* 拆分后的服务文件，SHALL 不直接导入跨模块的 Model
        
        **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
        **Validates: Requirements 5.6**
        """
        all_violations = []
        
        for file_path in self.get_all_decoupled_files():
            violations = check_file_for_cross_module_model_import(file_path)
            if violations:
                all_violations.append({
                    "file": file_path.name,
                    "violations": violations
                })
        
        if all_violations:
            error_msg = "发现直接导入跨模块 Model 的文件:\n"
            for v in all_violations:
                error_msg += f"\n{v['file']}:\n"
                for line_no, line_content in v['violations']:
                    error_msg += f"  行 {line_no}: {line_content}\n"
            
            assert False, error_msg
    
    @pytest.mark.property_test
    def test_property_2_lazy_loading(self):
        """
        Property 2.3: 遵循延迟加载模式
        
        *For any* 拆分后的服务文件，如果有依赖，SHALL 使用 @property 进行延迟加载
        
        **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
        **Validates: Requirements 5.5**
        """
        violations = []
        
        for file_path in self.get_all_decoupled_files():
            if not check_file_has_lazy_loading(file_path):
                violations.append(file_path.name)
        
        assert len(violations) == 0, (
            f"以下文件有依赖但未使用 @property 延迟加载:\n" +
            "\n".join(f"  {f}" for f in violations)
        )
    
    @pytest.mark.property_test
    def test_property_2_dependency_injection_support(self):
        """
        Property 2.4: 支持依赖注入
        
        *For any* 拆分后的服务文件中的类，构造函数 SHALL 支持无参数实例化
        
        **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
        **Validates: Requirements 5.2**
        """
        all_violations = []
        
        for file_path in self.get_all_decoupled_files():
            violations = check_constructor_supports_di(file_path)
            if violations:
                all_violations.append({
                    "file": file_path.name,
                    "violations": violations
                })
        
        if all_violations:
            error_msg = "以下类不支持依赖注入（构造函数有必需参数）:\n"
            for v in all_violations:
                error_msg += f"\n{v['file']}:\n"
                for class_name, error in v['violations']:
                    error_msg += f"  {class_name}: {error}\n"
            
            assert False, error_msg
    
    @given(st.sampled_from(list(DECOUPLED_FILES.keys())))
    @settings(max_examples=100)
    @pytest.mark.property_test
    def test_property_2_architecture_compliance_property_based(self, relative_path: str):
        """
        Property 2: 架构合规性 (Property-Based)
        
        *For any* 拆分后的服务文件，SHALL 满足架构合规性要求
        
        **Feature: automation-document-sms-decoupling, Property 2: 架构合规性**
        **Validates: Requirements 5.1, 5.2, 5.4, 5.5, 5.6**
        """
        services_path = get_backend_path() / "apps" / "automation" / "services"
        file_path = services_path / relative_path
        
        # 如果文件不存在，跳过
        assume(file_path.exists())
        
        # 检查 @staticmethod
        staticmethod_violations = check_file_for_staticmethod(file_path)
        assert len(staticmethod_violations) == 0, (
            f"{file_path.name} 使用了 @staticmethod"
        )
        
        # 检查跨模块 Model 导入
        model_import_violations = check_file_for_cross_module_model_import(file_path)
        assert len(model_import_violations) == 0, (
            f"{file_path.name} 直接导入了跨模块 Model"
        )
        
        # 检查延迟加载
        assert check_file_has_lazy_loading(file_path), (
            f"{file_path.name} 有依赖但未使用 @property 延迟加载"
        )



class TestCrossModuleCallProperties:
    """
    Property 3: 跨模块调用规范
    
    *For any* 需要跨模块调用的服务，SHALL 通过 ServiceLocator 获取依赖，而非直接导入
    
    **Feature: automation-document-sms-decoupling, Property 3: 跨模块调用规范**
    **Validates: Requirements 3.4, 5.3**
    """
    
    def get_automation_services_path(self) -> Path:
        """获取 automation services 目录路径"""
        return get_backend_path() / "apps" / "automation" / "services"
    
    def get_all_decoupled_files(self) -> List[Path]:
        """获取所有拆分后的文件路径"""
        services_path = self.get_automation_services_path()
        files = []
        
        for relative_path in DECOUPLED_FILES.keys():
            full_path = services_path / relative_path
            if full_path.exists():
                files.append(full_path)
        
        return files
    
    def check_cross_module_call_compliance(self, file_path: Path) -> Tuple[bool, List[str]]:
        """
        检查文件的跨模块调用是否符合规范
        
        规范要求：
        1. 不直接导入其他模块的服务类（TYPE_CHECKING 块中的除外）
        2. 通过 ServiceLocator 获取跨模块服务
        
        Args:
            file_path: 文件路径
            
        Returns:
            (是否合规, 违规列表)
        """
        violations = []
        
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # 检查直接导入其他模块服务的模式
            direct_import_patterns = [
                (r"from\s+apps\.client\.services\.\w+\s+import\s+\w+Service", "client"),
                (r"from\s+apps\.cases\.services\.\w+\s+import\s+\w+Service", "cases"),
                (r"from\s+apps\.contracts\.services\.\w+\s+import\s+\w+Service", "contracts"),
                (r"from\s+apps\.organization\.services\.\w+\s+import\s+\w+Service", "organization"),
            ]
            
            # 检测 TYPE_CHECKING 块的范围
            in_type_checking = False
            type_checking_indent = 0
            
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                
                # 检测 TYPE_CHECKING 块开始
                if 'if TYPE_CHECKING:' in line:
                    in_type_checking = True
                    type_checking_indent = len(line) - len(line.lstrip())
                    continue
                
                # 检测 TYPE_CHECKING 块结束（缩进减少）
                if in_type_checking and stripped and not stripped.startswith('#'):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= type_checking_indent and not line.strip().startswith('from') and not line.strip().startswith('import'):
                        in_type_checking = False
                
                # 跳过 TYPE_CHECKING 块中的导入
                if in_type_checking:
                    continue
                
                for pattern, module in direct_import_patterns:
                    if re.search(pattern, line):
                        violations.append(
                            f"行 {i}: 直接导入 {module} 模块服务: {stripped}"
                        )
            
            # 检查是否正确使用 ServiceLocator（如果导入了的话）
            # 注意：导入 ServiceLocator 但不使用也是合规的（可能是为了将来使用）
            if 'ServiceLocator.' in content:
                # 验证 ServiceLocator 的使用方式
                correct_patterns = [
                    r'ServiceLocator\.get_\w+_service\(\)',
                    r'ServiceLocator\.get_\w+_client\(\)',
                    r'ServiceLocator\.get_\w+\(\)',
                ]
                
                has_correct_usage = any(
                    re.search(pattern, content)
                    for pattern in correct_patterns
                )
                
                if not has_correct_usage:
                    violations.append("使用了 ServiceLocator 但调用方式不正确")
            
        except Exception as e:
            violations.append(f"检查失败: {str(e)}")
        
        return len(violations) == 0, violations
    
    @pytest.mark.property_test
    def test_property_3_cross_module_call_compliance(self):
        """
        Property 3: 跨模块调用规范
        
        *For any* 需要跨模块调用的服务，SHALL 通过 ServiceLocator 获取依赖
        
        **Feature: automation-document-sms-decoupling, Property 3: 跨模块调用规范**
        **Validates: Requirements 3.4, 5.3**
        """
        all_violations = []
        
        for file_path in self.get_all_decoupled_files():
            is_compliant, violations = self.check_cross_module_call_compliance(file_path)
            if not is_compliant:
                all_violations.append({
                    "file": file_path.name,
                    "violations": violations
                })
        
        if all_violations:
            error_msg = "发现跨模块调用不合规的文件:\n"
            for v in all_violations:
                error_msg += f"\n{v['file']}:\n"
                for violation in v['violations']:
                    error_msg += f"  {violation}\n"
            
            assert False, error_msg
    
    @pytest.mark.property_test
    def test_property_3_service_locator_usage(self):
        """
        Property 3.1: ServiceLocator 使用正确性
        
        *For any* 使用 ServiceLocator 的文件，SHALL 正确导入和使用
        
        **Feature: automation-document-sms-decoupling, Property 3: 跨模块调用规范**
        **Validates: Requirements 5.3**
        """
        violations = []
        
        for file_path in self.get_all_decoupled_files():
            is_correct, error = check_file_uses_service_locator_correctly(file_path)
            if not is_correct:
                violations.append({
                    "file": file_path.name,
                    "error": error
                })
        
        if violations:
            error_msg = "ServiceLocator 使用不正确的文件:\n"
            for v in violations:
                error_msg += f"  {v['file']}: {v['error']}\n"
            
            assert False, error_msg
    
    @given(st.sampled_from(list(DECOUPLED_FILES.keys())))
    @settings(max_examples=100)
    @pytest.mark.property_test
    def test_property_3_cross_module_call_property_based(self, relative_path: str):
        """
        Property 3: 跨模块调用规范 (Property-Based)
        
        *For any* 拆分后的服务文件，跨模块调用 SHALL 通过 ServiceLocator 进行
        
        **Feature: automation-document-sms-decoupling, Property 3: 跨模块调用规范**
        **Validates: Requirements 3.4, 5.3**
        """
        services_path = get_backend_path() / "apps" / "automation" / "services"
        file_path = services_path / relative_path
        
        # 如果文件不存在，跳过
        assume(file_path.exists())
        
        # 检查跨模块调用合规性
        is_compliant, violations = self.check_cross_module_call_compliance(file_path)
        
        assert is_compliant, (
            f"{file_path.name} 跨模块调用不合规:\n" +
            "\n".join(f"  {v}" for v in violations)
        )


# ============ 综合测试 ============

class TestDecouplingComprehensiveCompliance:
    """综合合规性测试"""
    
    def get_automation_services_path(self) -> Path:
        """获取 automation services 目录路径"""
        return get_backend_path() / "apps" / "automation" / "services"
    
    @pytest.mark.property_test
    def test_comprehensive_decoupling_compliance(self):
        """
        综合测试：所有拆分后的文件合规性
        
        验证所有拆分后的文件满足：
        1. 文件行数限制
        2. 架构合规性
        3. 跨模块调用规范
        
        **Feature: automation-document-sms-decoupling**
        **Validates: Requirements 1.2, 2.2, 3.4, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**
        """
        services_path = self.get_automation_services_path()
        
        compliance_report = {
            "total_files": 0,
            "existing_files": 0,
            "compliant_files": 0,
            "violations": []
        }
        
        for relative_path, file_type in DECOUPLED_FILES.items():
            compliance_report["total_files"] += 1
            
            file_path = services_path / relative_path
            if not file_path.exists():
                continue
            
            compliance_report["existing_files"] += 1
            file_violations = []
            
            # 检查 1: 文件行数限制
            limit = FILE_LINE_LIMITS.get(file_type, FILE_LINE_LIMITS["default"])
            total_lines = count_total_lines(file_path)
            if total_lines > limit:
                file_violations.append(
                    f"行数超限: {total_lines} > {limit}"
                )
            
            # 检查 2: @staticmethod
            staticmethod_violations = check_file_for_staticmethod(file_path)
            if staticmethod_violations:
                file_violations.append(
                    f"使用了 @staticmethod ({len(staticmethod_violations)} 处)"
                )
            
            # 检查 3: 跨模块 Model 导入
            model_import_violations = check_file_for_cross_module_model_import(file_path)
            if model_import_violations:
                file_violations.append(
                    f"直接导入跨模块 Model ({len(model_import_violations)} 处)"
                )
            
            # 检查 4: 延迟加载
            if not check_file_has_lazy_loading(file_path):
                file_violations.append("有依赖但未使用 @property 延迟加载")
            
            # 检查 5: 依赖注入支持
            di_violations = check_constructor_supports_di(file_path)
            if di_violations:
                file_violations.append(
                    f"不支持依赖注入 ({len(di_violations)} 个类)"
                )
            
            # 检查 6: ServiceLocator 使用
            is_correct, error = check_file_uses_service_locator_correctly(file_path)
            if not is_correct:
                file_violations.append(f"ServiceLocator 使用不正确: {error}")
            
            if file_violations:
                compliance_report["violations"].append({
                    "file": file_path.name,
                    "type": file_type,
                    "violations": file_violations
                })
            else:
                compliance_report["compliant_files"] += 1
        
        # 计算合规率
        compliance_rate = (
            compliance_report["compliant_files"] / compliance_report["existing_files"] * 100
            if compliance_report["existing_files"] > 0 else 0
        )
        
        # 输出合规性报告
        print(f"\n=== 解耦架构合规性报告 ===")
        print(f"预期文件数: {compliance_report['total_files']}")
        print(f"已存在文件数: {compliance_report['existing_files']}")
        print(f"合规文件数: {compliance_report['compliant_files']}")
        print(f"合规率: {compliance_rate:.1f}%")
        
        if compliance_report["violations"]:
            print(f"\n违规详情:")
            for v in compliance_report["violations"]:
                print(f"\n  {v['file']} ({v['type']}):")
                for violation in v["violations"]:
                    print(f"    - {violation}")
        
        # 要求至少 80% 的合规率
        assert compliance_rate >= 80.0, (
            f"解耦架构合规率 {compliance_rate:.1f}% 低于要求的 80%。"
            f"违规文件: {[v['file'] for v in compliance_report['violations']]}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
