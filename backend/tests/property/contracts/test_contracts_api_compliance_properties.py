"""
合同模块 API 层架构合规性 Property-Based Testing

Feature: contracts-module-compliance
Validates: Requirements 1.1, 1.2, 6.1, 6.2
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pathlib import Path

# 合同模块 API 文件列表
CONTRACTS_API_FILES = [
    "contract_api.py",
    "contractfinance_api.py",
    "contractpayment_api.py",
    "contractreminder_api.py",
    "supplementary_agreement_api.py",
]


def get_contracts_api_path() -> Path:
    """获取 contracts API 目录路径"""
    return Path(__file__).parent.parent.parent.parent / "apps" / "contracts" / "api"


@pytest.mark.property_test
class TestContractsAPICompliance:
    """合同模块 API 层合规性测试"""

    def test_api_layer_no_http_error(self):
        """
        Property 1: API 层无 HttpError

        *For any* API file in the contracts module, scanning the file content
        should find zero instances of `raise HttpError`

        Feature: contracts-module-compliance, Property 1: API 层无 HttpError
        Validates: Requirements 1.1, 6.1
        """
        api_path = get_contracts_api_path()
        errors = []

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # 检查是否包含 raise HttpError
            if "raise HttpError" in content:
                # 找出具体行号
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if "raise HttpError" in line:
                        errors.append(f"{api_file}:{i} - 包含 'raise HttpError': {line.strip()}")

        assert len(errors) == 0, "API 层不应包含 raise HttpError（应由全局异常处理器处理）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_api_layer_no_business_logic_variables(self):
        """
        Property 2: API 层无业务逻辑变量

        *For any* API file in the contracts module, scanning the file content
        should find zero instances of business logic patterns like `finance_keys =`

        Feature: contracts-module-compliance, Property 2: API 层无业务逻辑变量
        Validates: Requirements 1.2
        """
        api_path = get_contracts_api_path()
        errors = []

        # 业务逻辑变量模式
        business_logic_patterns = [
            "finance_keys =",
            "touch_finance =",
            "finance_keys=",
            "touch_finance=",
        ]

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            for pattern in business_logic_patterns:
                if pattern in content:
                    # 找出具体行号
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if pattern in line:
                            errors.append(f"{api_file}:{i} - 包含业务逻辑变量 '{pattern}': {line.strip()}")

        assert len(errors) == 0, "API 层不应包含业务逻辑变量（应在 Service 层处理）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_api_layer_no_is_admin_checks(self):
        """
        Property 7: API 层无权限检查

        *For any* API file in the contracts module, scanning the file content
        should find zero instances of `is_admin` checks outside of parameter extraction

        Feature: contracts-module-compliance, Property 7: API 层无权限检查
        Validates: Requirements 6.2
        """
        api_path = get_contracts_api_path()
        errors = []

        # 权限检查模式（排除参数提取）
        permission_patterns = [
            ("if not is_admin", "权限判断"),
            ("if is_admin", "权限判断"),
            ("not request.user.is_admin", "权限判断"),
            ("request.user.is_admin", "权限判断"),
        ]

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern, desc in permission_patterns:
                    if pattern in line:
                        # 检查是否是参数提取（getattr 模式是允许的）
                        if "getattr" in line and "is_admin" in line:
                            continue
                        errors.append(f"{api_file}:{i} - 包含{desc} '{pattern}': {stripped}")

        assert len(errors) == 0, "API 层不应包含权限检查（应在 Service 层处理）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_api_layer_has_factory_function(self):
        """
        API 层应有工厂函数

        *For any* API file in the contracts module, it should define a factory
        function for creating Service instances

        Validates: Requirements 1.5
        """
        api_path = get_contracts_api_path()
        errors = []

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # 检查是否有工厂函数（def _get_xxx_service）
            if "def _get_" not in content:
                errors.append(f"{api_file} - 缺少工厂函数 (def _get_xxx_service)")

        assert len(errors) == 0, "API 层应有工厂函数用于创建 Service 实例:\n" + "\n".join(f"  - {e}" for e in errors)

    def test_api_layer_no_direct_model_operations(self):
        """
        API 层无直接 Model 操作

        *For any* API file in the contracts module, it should not contain
        direct Model operations like .objects.filter() or .objects.create()

        Validates: Requirements 1.3
        """
        api_path = get_contracts_api_path()
        errors = []

        # Model 操作模式
        model_operation_patterns = [
            ".objects.filter(",
            ".objects.get(",
            ".objects.create(",
            ".objects.update(",
            ".objects.delete(",
            ".objects.all(",
            ".objects.exclude(",
        ]

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern in model_operation_patterns:
                    if pattern in line:
                        errors.append(f"{api_file}:{i} - 包含直接 Model 操作 '{pattern}': {stripped}")

        assert len(errors) == 0, "API 层不应包含直接 Model 操作（应在 Service 层处理）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_api_layer_no_try_except(self):
        """
        API 层无 try/except

        *For any* API file in the contracts module, it should not contain
        try/except blocks (exceptions should be handled by global handler)

        Validates: Requirements 1.3
        """
        api_path = get_contracts_api_path()
        errors = []

        for api_file in CONTRACTS_API_FILES:
            file_path = api_path / api_file
            if not file_path.exists():
                continue

            content = file_path.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                # 检查 try: 语句
                if stripped == "try:" or stripped.startswith("try:"):
                    errors.append(f"{api_file}:{i} - 包含 try/except 块: {stripped}")

        assert len(errors) == 0, "API 层不应包含 try/except 块（异常应由全局处理器处理）:\n" + "\n".join(
            f"  - {e}" for e in errors
        )


@given(st.sampled_from(CONTRACTS_API_FILES))
@settings(max_examples=len(CONTRACTS_API_FILES))
@pytest.mark.property_test
def test_api_file_compliance_property(api_file: str):
    """
    Property: API 文件合规性

    *For any* API file in the contracts module, it should comply with
    all architecture rules

    Feature: contracts-module-compliance
    Validates: Requirements 1.1, 1.2, 6.1, 6.2
    """
    api_path = get_contracts_api_path()
    file_path = api_path / api_file

    if not file_path.exists():
        pytest.skip(f"API file {api_file} does not exist")

    content = file_path.read_text()

    # 检查无 HttpError
    assert "raise HttpError" not in content, f"{api_file} 包含 'raise HttpError'，应由全局异常处理器处理"

    # 检查无业务逻辑变量
    assert "finance_keys =" not in content, f"{api_file} 包含业务逻辑变量 'finance_keys'，应在 Service 层处理"
    assert "touch_finance =" not in content, f"{api_file} 包含业务逻辑变量 'touch_finance'，应在 Service 层处理"

    # 检查有工厂函数
    assert "def _get_" in content, f"{api_file} 缺少工厂函数 (def _get_xxx_service)"
