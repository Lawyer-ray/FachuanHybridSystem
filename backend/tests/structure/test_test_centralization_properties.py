"""
测试文件集中性 Property-Based Tests

Feature: backend-structure-optimization, Property 2: 测试文件集中性
Feature: backend-cleanup-optimization, Property 3: 测试工具集中化
Validates: Requirements 2.1, 2.2, 3.1, 3.2
"""

from pathlib import Path
from typing import List

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st


class TestTestCentralization:
    """测试文件集中性属性测试"""

    @pytest.fixture
    def backend_root(self) -> Path:
        """获取 backend 根目录"""
        return Path(__file__).parent.parent.parent

    def test_no_test_files_in_app_tests_directories(self, backend_root: Path):
        """
        Property 2.1: apps/*/tests/ 目录不应包含测试文件

        所有测试文件应该已经迁移到集中的 tests/ 目录

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.1
        """
        apps_path = backend_root / "apps"

        # 扫描所有 app 的 tests 目录
        test_files_in_apps = []
        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir() or app_dir.name == "tests":
                continue

            tests_dir = app_dir / "tests"
            if tests_dir.exists() and tests_dir.is_dir():
                # 查找测试文件
                for test_file in tests_dir.rglob("test*.py"):
                    if test_file.is_file():
                        test_files_in_apps.append(test_file)

        # 断言：不应该有测试文件在 apps/*/tests/ 目录
        assert (
            len(test_files_in_apps) == 0
        ), f"发现 {len(test_files_in_apps)} 个测试文件仍在 apps/*/tests/ 目录:\n" + "\n".join(
            str(f) for f in test_files_in_apps
        )

    def test_all_test_files_in_centralized_tests_directory(self, backend_root: Path):
        """
        Property 2.2: 所有测试文件应该在集中的 tests/ 目录

        测试文件应该按类型组织在 tests/unit/, tests/integration/, tests/property/

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.1, 2.2
        """
        tests_path = backend_root / "tests"

        # 查找所有测试文件
        test_files = list(tests_path.rglob("test*.py"))

        # 断言：应该有测试文件
        assert len(test_files) > 0, "tests/ 目录应该包含测试文件"

        # 验证测试文件的位置
        valid_test_dirs = [
            "unit",
            "integration",
            "property",
            "admin",
            "structure",
            "documents",
            "litigation_ai",
            "e2e",
            "core",
        ]
        invalid_test_files = []

        for test_file in test_files:
            # 获取相对于 tests/ 的路径
            relative_path = test_file.relative_to(tests_path)

            # 检查是否在有效的测试目录中
            if len(relative_path.parts) > 0:
                top_level_dir = relative_path.parts[0]
                if top_level_dir not in valid_test_dirs:
                    invalid_test_files.append(test_file)

        # 断言：所有测试文件应该在有效的测试目录中
        assert (
            len(invalid_test_files) == 0
        ), f"发现 {len(invalid_test_files)} 个测试文件不在有效的测试目录中:\n" + "\n".join(
            str(f) for f in invalid_test_files
        )

    def test_api_tests_in_integration_directory(self, backend_root: Path):
        """
        Property 2.3: API 测试应该在 integration/ 目录

        所有包含 _api 或 api_ 的测试文件应该在 tests/integration/
        （除非同时包含 properties，那应该在 property/ 目录）

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.2
        """
        tests_path = backend_root / "tests"

        # 查找所有 API 测试文件
        api_test_files = []
        for test_file in tests_path.rglob("test*api*.py"):
            if test_file.is_file():
                # 如果同时包含 properties，则跳过（应该在 property/ 目录）
                if "properties" not in test_file.name:
                    api_test_files.append(test_file)

        # 验证 API 测试文件的位置
        misplaced_api_tests = []
        for test_file in api_test_files:
            relative_path = test_file.relative_to(tests_path)
            if len(relative_path.parts) > 0:
                top_level_dir = relative_path.parts[0]
                if top_level_dir not in {"integration", "unit", "documents", "structure"}:
                    misplaced_api_tests.append(test_file)

        assert (
            len(misplaced_api_tests) == 0
        ), f"发现 {len(misplaced_api_tests)} 个 API 测试文件位置不符合约定:\n" + "\n".join(
            str(f) for f in misplaced_api_tests
        )

    def test_property_tests_in_property_directory(self, backend_root: Path):
        """
        Property 2.4: Property-based 测试应该在 property/ 目录

        所有包含 _properties 或 properties_ 的测试文件应该在 tests/property/
        （除了 structure/ 目录中的结构验证测试）

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.2
        """
        tests_path = backend_root / "tests"

        # 查找所有 property-based 测试文件
        property_test_files = []
        for test_file in tests_path.rglob("test*properties*.py"):
            if test_file.is_file():
                property_test_files.append(test_file)

        # 验证 property-based 测试文件的位置
        misplaced_property_tests = []
        for test_file in property_test_files:
            relative_path = test_file.relative_to(tests_path)
            if len(relative_path.parts) > 0:
                top_level_dir = relative_path.parts[0]
                # structure/ 目录中的 property 测试是例外（用于验证项目结构）
                if top_level_dir not in ["property", "structure"]:
                    misplaced_property_tests.append(test_file)

        # 断言：所有 property-based 测试应该在 property/ 或 structure/ 目录
        assert (
            len(misplaced_property_tests) == 0
        ), f"发现 {len(misplaced_property_tests)} 个 property-based 测试文件不在 property/ 或 structure/ 目录:\n" + "\n".join(
            str(f) for f in misplaced_property_tests
        )

    def test_factories_in_centralized_factories_directory(self, backend_root: Path):
        """
        Property 2.5: Factory 文件应该在集中的 factories/ 目录

        所有 factory 文件应该在 tests/factories/，不应该在 apps/tests/factories/

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.1
        """
        apps_tests_factories = backend_root / "apps" / "tests" / "factories"

        # 检查 apps/tests/factories/ 是否还有文件
        factory_files_in_apps = []
        if apps_tests_factories.exists():
            for factory_file in apps_tests_factories.rglob("*.py"):
                if factory_file.is_file() and factory_file.name != "__init__.py":
                    factory_files_in_apps.append(factory_file)

        # 断言：apps/tests/factories/ 不应该有 factory 文件
        assert (
            len(factory_files_in_apps) == 0
        ), f"发现 {len(factory_files_in_apps)} 个 factory 文件仍在 apps/tests/factories/:\n" + "\n".join(
            str(f) for f in factory_files_in_apps
        )

        # 验证 tests/factories/ 有 factory 文件
        tests_factories = backend_root / "tests" / "factories"
        factory_files_in_tests = []
        if tests_factories.exists():
            for factory_file in tests_factories.rglob("*_factories.py"):
                if factory_file.is_file():
                    factory_files_in_tests.append(factory_file)

        # 断言：tests/factories/ 应该有 factory 文件
        assert len(factory_files_in_tests) > 0, "tests/factories/ 应该包含 factory 文件"

    def test_mocks_in_centralized_mocks_directory(self, backend_root: Path):
        """
        Property 2.6: Mock 文件应该在集中的 mocks/ 目录

        所有 mock 文件应该在 tests/mocks/，不应该在 apps/tests/mocks/

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.1
        """
        apps_tests_mocks = backend_root / "apps" / "tests" / "mocks"

        # 检查 apps/tests/mocks/ 是否还有文件
        mock_files_in_apps = []
        if apps_tests_mocks.exists():
            for mock_file in apps_tests_mocks.rglob("*.py"):
                if mock_file.is_file() and mock_file.name != "__init__.py":
                    mock_files_in_apps.append(mock_file)

        # 断言：apps/tests/mocks/ 不应该有 mock 文件
        assert (
            len(mock_files_in_apps) == 0
        ), f"发现 {len(mock_files_in_apps)} 个 mock 文件仍在 apps/tests/mocks/:\n" + "\n".join(
            str(f) for f in mock_files_in_apps
        )

        # 验证 tests/mocks/ 有 mock 文件
        tests_mocks = backend_root / "tests" / "mocks"
        mock_files_in_tests = []
        if tests_mocks.exists():
            for mock_file in tests_mocks.rglob("*.py"):
                if mock_file.is_file() and mock_file.name != "__init__.py":
                    mock_files_in_tests.append(mock_file)

        # 断言：tests/mocks/ 应该有 mock 文件
        assert len(mock_files_in_tests) > 0, "tests/mocks/ 应该包含 mock 文件"

    @given(st.sampled_from(["unit", "integration", "property"]))
    @pytest.mark.hypothesis
    def test_test_directory_structure_consistency(self, test_type: str):
        """
        Property 2.7: 测试目录结构一致性

        对于任何测试类型（unit/integration/property），
        其子目录应该按模块组织（cases/, contracts/, etc.）

        Feature: backend-structure-optimization, Property 2: 测试文件集中性
        Validates: Requirements 2.2
        """
        # 直接获取 backend_root，避免使用 fixture
        backend_root = Path(__file__).parent.parent.parent
        test_dir = backend_root / "tests" / test_type

        if not test_dir.exists():
            pytest.skip(f"{test_type} 目录不存在")

        # 获取所有子目录
        subdirs = [d for d in test_dir.iterdir() if d.is_dir() and not d.name.startswith("__")]

        if len(subdirs) == 0:
            pytest.skip(f"{test_type} 目录没有子目录")

        # 验证子目录名称是否是有效的模块名
        valid_module_names = [
            "cases",
            "contracts",
            "client",
            "organization",
            "automation",
            "chat_records",
            "core",
            "documents",
            "litigation_ai",
            "onboarding",
            "refactoring",
        ]

        invalid_subdirs = []
        for subdir in subdirs:
            if subdir.name not in valid_module_names:
                invalid_subdirs.append(subdir)

        # 断言：所有子目录应该是有效的模块名
        assert len(invalid_subdirs) == 0, f"发现 {len(invalid_subdirs)} 个无效的子目录在 {test_type}/:\n" + "\n".join(
            str(d) for d in invalid_subdirs
        )

    def test_strategies_in_centralized_strategies_directory(self, backend_root: Path):
        """
        Property 3: 测试工具集中化 - Strategies 文件应该在集中的 strategies/ 目录

        所有 strategy 文件应该在 tests/strategies/，不应该在 apps/tests/strategies/

        Feature: backend-cleanup-optimization, Property 3: 测试工具集中化
        Validates: Requirements 3.1, 3.2
        """
        apps_tests_strategies = backend_root / "apps" / "tests" / "strategies"

        # 检查 apps/tests/strategies/ 是否还有文件
        strategy_files_in_apps = []
        if apps_tests_strategies.exists():
            for strategy_file in apps_tests_strategies.rglob("*.py"):
                if strategy_file.is_file() and strategy_file.name != "__init__.py":
                    strategy_files_in_apps.append(strategy_file)

        # 断言：apps/tests/strategies/ 不应该有 strategy 文件
        assert (
            len(strategy_files_in_apps) == 0
        ), f"发现 {len(strategy_files_in_apps)} 个 strategy 文件仍在 apps/tests/strategies/:\n" + "\n".join(
            str(f) for f in strategy_files_in_apps
        )

        # 验证 tests/strategies/ 有 strategy 文件
        tests_strategies = backend_root / "tests" / "strategies"
        strategy_files_in_tests = []
        if tests_strategies.exists():
            for strategy_file in tests_strategies.rglob("*_strategies.py"):
                if strategy_file.is_file():
                    strategy_files_in_tests.append(strategy_file)

        # 断言：tests/strategies/ 应该有 strategy 文件
        assert len(strategy_files_in_tests) > 0, "tests/strategies/ 应该包含 strategy 文件"

    def test_apps_tests_directory_only_contains_init(self, backend_root: Path):
        """
        Property 3.2: apps/tests/ 目录应该只包含 __init__.py

        迁移完成后，apps/tests/ 目录应该只保留 __init__.py 文件，
        所有其他测试工具（factories, mocks, strategies, utils.py, README.md）
        都应该已经迁移或删除。

        Feature: backend-cleanup-optimization, Property 3: 测试工具集中化
        Validates: Requirements 3.2
        """
        apps_tests = backend_root / "apps" / "tests"

        if not apps_tests.exists():
            # 如果目录不存在，测试通过
            return

        # 获取所有文件和目录（排除 __pycache__）
        remaining_items = []
        for item in apps_tests.iterdir():
            if item.name == "__pycache__":
                continue
            if item.name == "__init__.py":
                continue
            remaining_items.append(item)

        # 断言：apps/tests/ 应该只有 __init__.py
        assert len(remaining_items) == 0, "apps/tests/ 目录应该只包含 __init__.py，但发现以下文件/目录:\n" + "\n".join(
            str(item) for item in remaining_items
        )
