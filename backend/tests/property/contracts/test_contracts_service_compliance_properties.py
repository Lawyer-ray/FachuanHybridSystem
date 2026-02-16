"""
合同模块 Service 层架构合规性 Property-Based Testing

Feature: contracts-module-compliance
Validates: Requirements 6.3, 6.4
"""

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.path import Path

# 合同模块 Service 文件列表
CONTRACTS_SERVICE_FILES = [
    "contract_service.py",
    "contract_finance_service.py",
    "contract_payment_service.py",
    "contract_reminder_service.py",
    "lawyer_assignment_service.py",
    "supplementary_agreement_service.py",
]


def get_contracts_service_path() -> Path:
    """获取 contracts Service 目录路径"""
    return Path(__file__).parent.parent.parent.parent / "apps" / "contracts" / "services"


def extract_method_bodies(content: str) -> list[tuple[str, str, int]]:
    """
    提取类方法体（排除 __init__ 和 @property）

    Returns:
        列表，每个元素为 (方法名, 方法体, 起始行号)
    """
    methods = []
    lines = content.split("\n")

    in_method = False
    method_name = ""
    method_body = []
    method_start_line = 0
    method_indent = 0
    is_property = False

    for i, line in enumerate(lines, 1):
        # 检查是否是 @property 装饰器
        if line.strip() == "@property":
            is_property = True
            continue

        # 检查是否是方法定义
        method_match = re.match(r"^(\s*)def\s+(\w+)\s*\(", line)
        if method_match:
            # 保存之前的方法
            if in_method and method_body:
                methods.append((method_name, "\n".join(method_body), method_start_line))

            indent = len(method_match.group(1))
            name = method_match.group(2)

            # 跳过 __init__ 和 property 方法
            if name == "__init__" or is_property:
                in_method = False
                is_property = False
                method_body = []
                continue

            in_method = True
            method_name = name
            method_body = [line]
            method_start_line = i
            method_indent = indent
            is_property = False
            continue

        # 如果在方法内部
        if in_method:
            # 检查是否是方法结束（遇到同级或更低缩进的非空行）
            if line.strip() and not line.startswith(" " * (method_indent + 1)):
                # 方法结束
                methods.append((method_name, "\n".join(method_body), method_start_line))
                in_method = False
                method_body = []
            else:
                method_body.append(line)

    # 保存最后一个方法
    if in_method and method_body:
        methods.append((method_name, "\n".join(method_body), method_start_line))

    return methods


@pytest.mark.property_test
class TestContractsServiceCompliance:
    """合同模块 Service 层合规性测试"""

    def test_service_no_method_internal_instantiation(self):
        """
        Property 8: Service 无方法内实例化

        *For any* Service class in the contracts module, scanning method bodies
        (excluding `__init__` and property accessors) should find zero direct
        Service instantiations

        Feature: contracts-module-compliance, Property 8: Service 无方法内实例化
        Validates: Requirements 6.3
        """
        service_path = get_contracts_service_path()
        errors = []

        # Service 实例化模式
        service_instantiation_patterns = [
            (r"(\w+Service)\s*\(", "Service 实例化"),
            (r"(\w+ServiceAdapter)\s*\(", "ServiceAdapter 实例化"),
        ]

        for service_file in CONTRACTS_SERVICE_FILES:
            file_path = service_path / service_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # 提取方法体（排除 __init__ 和 property）
            methods = extract_method_bodies(content)

            for method_name, method_body, start_line in methods:
                # 跳过私有方法中的某些特殊情况
                if method_name.startswith("_") and method_name != "__init__":
                    # 私有方法可能有特殊需求，但仍需检查
                    pass

                for pattern, desc in service_instantiation_patterns:
                    matches = re.finditer(pattern, method_body)
                    for match in matches:
                        service_name = match.group(1)
                        # 计算实际行号
                        match_pos = match.start()
                        lines_before = method_body[:match_pos].count("\n")
                        actual_line = start_line + lines_before

                        # 检查是否在注释中
                        line_content = method_body.split("\n")[lines_before]
                        if line_content.strip().startswith("#"):
                            continue

                        errors.append(
                            f"{service_file}:{actual_line} - 方法 {method_name} 中包含 {desc}: {service_name}"
                        )

        assert len(errors) == 0, f"Service 方法内不应直接实例化其他 Service（应通过构造函数注入）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_service_has_constructor_injection(self):
        """
        Service 应支持构造函数注入

        *For any* Service class in the contracts module, it should have a
        constructor that supports dependency injection

        Validates: Requirements 6.4
        """
        service_path = get_contracts_service_path()
        errors = []

        for service_file in CONTRACTS_SERVICE_FILES:
            file_path = service_path / service_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # 检查是否有 __init__ 方法
            if "def __init__" not in content:
                errors.append(f"{service_file} - 缺少 __init__ 方法（应支持依赖注入）")
                continue

            # 检查 __init__ 是否有可选参数（依赖注入模式）
            init_match = re.search(r"def __init__\s*\([^)]+\)", content, re.DOTALL)
            if init_match:
                init_signature = init_match.group(0)
                # 检查是否有 Optional 或 = None 参数
                if "Optional" not in init_signature and "= None" not in init_signature:
                    # 可能只有 self 参数，这是允许的
                    if init_signature.count(",") > 0:
                        errors.append(f"{service_file} - __init__ 方法应支持可选依赖注入参数")

        assert len(errors) == 0, f"Service 应支持构造函数依赖注入:\n" + "\n".join(f"  - {e}" for e in errors)

    def test_service_uses_property_accessors(self):
        """
        Service 应使用属性访问器获取依赖

        *For any* Service class in the contracts module that has injected
        dependencies, it should use @property accessors for lazy loading

        Validates: Requirements 2.2, 2.3
        """
        service_path = get_contracts_service_path()

        # 只检查 contract_service.py，因为它是主要的服务类
        file_path = service_path / "contract_service.py"
        if not file_path.exists():
            pytest.skip("contract_service.py not found")

        content = file_path.read_text()

        # 检查是否有 @property 装饰器
        property_count = content.count("@property")

        # ContractService 应该有多个 property 访问器
        assert property_count >= 3, (
            f"ContractService 应有多个 @property 访问器用于延迟获取依赖，" f"当前只有 {property_count} 个"
        )

    def test_service_no_http_error(self):
        """
        Service 层无 HttpError

        *For any* Service file in the contracts module, it should not contain
        HttpError (should use business exceptions instead)

        Validates: Requirements 4.2
        """
        service_path = get_contracts_service_path()
        errors = []

        for service_file in CONTRACTS_SERVICE_FILES:
            file_path = service_path / service_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # 检查是否包含 HttpError
            if "HttpError" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if "HttpError" in line:
                        errors.append(f"{service_file}:{i} - 包含 HttpError: {line.strip()}")

        assert len(errors) == 0, f"Service 层不应使用 HttpError（应使用业务异常如 ValidationException）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_service_uses_business_exceptions(self):
        """
        Service 层使用业务异常

        *For any* Service file in the contracts module, it should use
        business exceptions from apps.core.exceptions

        Validates: Requirements 4.2
        """
        service_path = get_contracts_service_path()

        # 检查 contract_service.py
        file_path = service_path / "contract_service.py"
        if not file_path.exists():
            pytest.skip("contract_service.py not found")

        content = file_path.read_text()

        # 检查是否导入了业务异常
        assert "from apps.core.exceptions import" in content, "ContractService 应从 apps.core.exceptions 导入业务异常"

        # 检查是否使用了业务异常
        business_exceptions = [
            "NotFoundError",
            "ValidationException",
            "PermissionDenied",
        ]

        used_exceptions = [exc for exc in business_exceptions if exc in content]
        assert len(used_exceptions) >= 2, f"ContractService 应使用业务异常，当前使用: {used_exceptions}"


@given(st.sampled_from(CONTRACTS_SERVICE_FILES))
@settings(max_examples=len(CONTRACTS_SERVICE_FILES))
@pytest.mark.property_test
def test_service_file_compliance_property(service_file: str):
    """
    Property: Service 文件合规性

    *For any* Service file in the contracts module, it should comply with
    all architecture rules

    Feature: contracts-module-compliance
    Validates: Requirements 6.3, 6.4
    """
    service_path = get_contracts_service_path()
    file_path = service_path / service_file

    if not file_path.exists():
        pytest.skip(f"Service file {service_file} does not exist")

    content = file_path.read_text()

    # 检查无 HttpError
    assert "raise HttpError" not in content, f"{service_file} 包含 'raise HttpError'，应使用业务异常"

    # 检查有 __init__ 方法
    assert "def __init__" in content, f"{service_file} 缺少 __init__ 方法"
