"""
空目录移除 Property-Based Tests

Feature: backend-cleanup-optimization, Property 8: 空目录移除
Validates: Requirements 7.1
"""

from typing import List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pathlib import Path


class TestEmptyDirectoryRemoval:
    """空目录移除属性测试"""

    @pytest.fixture
    def backend_root(self) -> Path:
        """获取 backend 根目录"""
        return Path(__file__).parent.parent.parent

    def _is_empty_test_directory(self, directory: Path) -> bool:
        """
        检查目录是否为空测试目录（只包含 __init__.py 和/或 __pycache__）

        Args:
            directory: 要检查的目录路径

        Returns:
            True 如果目录只包含 __init__.py 和/或 __pycache__
        """
        if not directory.exists() or not directory.is_dir():
            return False

        for item in directory.iterdir():
            # 忽略 __pycache__ 目录
            if item.name == "__pycache__":
                continue
            # 忽略 __init__.py 文件
            if item.name == "__init__.py":
                continue
            # 如果有其他文件或目录，则不是空目录
            return False

        return True

    def test_no_empty_test_directories_in_apps(self, backend_root: Path):
        """
        Property 8: 空目录移除

        *For any* `apps/*/tests/` directory that only contains `__init__.py`,
        it should be removed after cleanup.

        Feature: backend-cleanup-optimization, Property 8: 空目录移除
        Validates: Requirements 7.1
        """
        apps_path = backend_root / "apps"

        # 收集所有空的测试目录
        empty_test_dirs = []

        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir():
                continue
            # 跳过 apps/tests 目录（这是测试工具目录，不是 app 的测试目录）
            if app_dir.name == "tests":
                continue

            tests_dir = app_dir / "tests"
            if tests_dir.exists() and self._is_empty_test_directory(tests_dir):
                empty_test_dirs.append(tests_dir)

        # 断言：不应该有空的测试目录
        assert len(empty_test_dirs) == 0, f"发现 {len(empty_test_dirs)} 个空的测试目录应该被删除:\n" + "\n".join(
            str(d) for d in empty_test_dirs
        )

    @given(st.sampled_from(["cases", "client", "contracts", "organization", "core", "automation"]))
    @settings(max_examples=6)
    @pytest.mark.hypothesis
    def test_app_test_directory_not_empty_or_removed(self, app_name: str):
        """
        Property 8.1: 对于任何 app 模块，其 tests/ 目录要么包含实际测试文件，要么已被删除

        Feature: backend-cleanup-optimization, Property 8: 空目录移除
        Validates: Requirements 7.1
        """
        backend_root = Path(__file__).parent.parent.parent
        tests_dir = backend_root / "apps" / app_name / "tests"

        if not tests_dir.exists():
            # 目录不存在，测试通过（已被删除）
            return

        # 如果目录存在，检查是否为空
        has_content = False
        for item in tests_dir.iterdir():
            if item.name == "__pycache__":
                continue
            if item.name == "__init__.py":
                continue
            # 找到其他内容
            has_content = True
            break

        # 断言：如果目录存在，必须有实际内容
        assert has_content, f"apps/{app_name}/tests/ 目录存在但只包含 __init__.py，应该被删除"

    def test_no_orphaned_pycache_directories(self, backend_root: Path):
        """
        Property 8.2: 删除空测试目录后不应该留下孤立的 __pycache__ 目录

        Feature: backend-cleanup-optimization, Property 8: 空目录移除
        Validates: Requirements 7.2
        """
        apps_path = backend_root / "apps"

        # 收集所有只有 __pycache__ 的目录
        orphaned_pycache_dirs = []

        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir():
                continue
            if app_dir.name == "tests":
                continue

            tests_dir = app_dir / "tests"
            if tests_dir.exists() and tests_dir.is_dir():
                # 检查是否只有 __pycache__
                items = list(tests_dir.iterdir())
                if len(items) == 1 and items[0].name == "__pycache__":
                    orphaned_pycache_dirs.append(tests_dir)

        # 断言：不应该有只包含 __pycache__ 的目录
        assert (
            len(orphaned_pycache_dirs) == 0
        ), f"发现 {len(orphaned_pycache_dirs)} 个只包含 __pycache__ 的目录:\n" + "\n".join(
            str(d) for d in orphaned_pycache_dirs
        )
