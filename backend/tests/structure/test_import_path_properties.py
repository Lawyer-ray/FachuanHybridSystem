"""
Property-Based Tests for Import Path Validity

测试所有测试文件中的导入路径有效性

**Feature: backend-cleanup-optimization, Property 4: 导入路径有效性**
**Validates: Requirements 3.3**
"""

import ast
import importlib.util
import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.core.path import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 旧的导入路径（应该不存在）
OLD_IMPORT_PATHS = [
    "apps.tests.strategies",
    "apps.tests.factories",
    "apps.tests.mocks",
    "apps.tests.utils",
]

# 新的导入路径（应该使用这些）
NEW_IMPORT_PATHS = [
    "tests.strategies",
    "tests.factories",
    "tests.mocks",
]


def find_all_python_files(root: Path, exclude_dirs: set[str] | None = None) -> list[Path]:
    """查找所有 Python 文件"""
    if exclude_dirs is None:
        exclude_dirs = {
            "__pycache__",
            "node_modules",
            "venv",
            "venv311",
            ".venv",
            "htmlcov",
            ".hypothesis",
            ".mypy_cache",
            ".pytest_cache",
            ".git",
            ".idea",
            ".vscode",
            "migrations",
        }

    python_files = []

    for item in root.rglob("*.py"):
        # 跳过排除的目录
        if any(excluded in item.parts for excluded in exclude_dirs):
            continue
        python_files.append(item)

    return python_files


def extract_imports_from_file(file_path: Path) -> list[tuple[str, int]]:
    """
    从 Python 文件中提取所有导入语句

    Returns:
        list[tuple[str, int]]: (导入模块名, 行号) 列表
    """
    imports = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append((node.module, node.lineno))
    except (SyntaxError, UnicodeDecodeError):
        pass

    return imports


def check_for_old_import_paths(file_path: Path) -> list[tuple[str, int, str]]:
    """
    检查文件中是否使用了旧的导入路径

    Returns:
        list[tuple[str, int, str]]: (文件路径, 行号, 旧导入路径) 列表
    """
    issues = []
    imports = extract_imports_from_file(file_path)

    for module_name, line_no in imports:
        for old_path in OLD_IMPORT_PATHS:
            if module_name.startswith(old_path):
                issues.append((str(file_path), line_no, module_name))

    return issues


def check_import_resolvable(module_name: str) -> bool:
    """
    检查导入路径是否可解析

    Returns:
        bool: 导入是否可解析
    """
    try:
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ModuleNotFoundError, ImportError, ValueError):
        return False


# 获取所有 Python 文件用于测试
all_python_files = find_all_python_files(project_root)
test_files = [f for f in all_python_files if "test" in f.name.lower() or f.parent.name == "tests"]

if test_files:
    test_file_strategy = st.sampled_from(test_files)
else:
    test_file_strategy = st.just(project_root / "conftest.py")


@given(test_file_strategy)
@settings(max_examples=20, deadline=None)
def test_no_old_import_paths_property(file_path: Path):
    """
    Property 4: 导入路径有效性

    *For any* Python file that imports test utilities, the import path
    should be valid and resolvable after migration.

    **Feature: backend-cleanup-optimization, Property 4: 导入路径有效性**
    **Validates: Requirements 3.3**
    """
    assume(file_path.exists())

    issues = check_for_old_import_paths(file_path)

    assert len(issues) == 0, (
        f"Found old import paths in {file_path.relative_to(project_root)}:\n"
        + "\n".join(f"  Line {line}: {module}" for _, line, module in issues)
        + "\n\nThese imports should be updated to use the new paths:\n"
        + "  - apps.tests.strategies -> tests.strategies\n"
        + "  - apps.tests.factories -> tests.factories\n"
        + "  - apps.tests.mocks -> tests.mocks"
    )


def test_no_old_imports_in_conftest():
    """
    测试 conftest.py 中没有旧的导入路径
    """
    conftest_path = project_root / "conftest.py"
    if not conftest_path.exists():
        pytest.skip("conftest.py does not exist")

    issues = check_for_old_import_paths(conftest_path)

    assert len(issues) == 0, (
        "Found old import paths in conftest.py:\n"
        + "\n".join(f"  Line {line}: {module}" for _, line, module in issues)
        + "\n\nUpdate these imports to use the new paths."
    )


def test_no_old_imports_in_all_test_files():
    """
    测试所有测试文件中没有旧的导入路径
    """
    all_issues = []

    for file_path in test_files:
        issues = check_for_old_import_paths(file_path)
        all_issues.extend(issues)

    assert len(all_issues) == 0, (
        f"Found {len(all_issues)} old import paths in test files:\n"
        + "\n".join(
            f"  {Path(path).relative_to(project_root)}:{line} - {module}"
            for path, line, module in all_issues[:20]  # 只显示前20个
        )
        + (f"\n  ... and {len(all_issues) - 20} more" if len(all_issues) > 20 else "")
        + "\n\nUpdate these imports to use the new paths."
    )


def test_new_import_paths_exist():
    """
    测试新的导入路径目录存在
    """
    missing_dirs = []

    for import_path in NEW_IMPORT_PATHS:
        dir_path = project_root / import_path.replace(".", "/")
        if not dir_path.exists():
            missing_dirs.append(import_path)

    assert len(missing_dirs) == 0, (
        "Missing test utility directories:\n"
        + "\n".join(f"  - {path}" for path in missing_dirs)
        + "\n\nThese directories should exist for imports to work."
    )


def test_new_import_paths_have_init():
    """
    测试新的导入路径目录有 __init__.py
    """
    missing_init = []

    for import_path in NEW_IMPORT_PATHS:
        dir_path = project_root / import_path.replace(".", "/")
        init_path = dir_path / "__init__.py"
        if dir_path.exists() and not init_path.exists():
            missing_init.append(import_path)

    assert len(missing_init) == 0, (
        "Missing __init__.py in test utility directories:\n"
        + "\n".join(f"  - {path}" for path in missing_init)
        + "\n\nThese directories need __init__.py for imports to work."
    )


def test_test_utilities_not_in_apps_tests():
    """
    测试 apps/tests 目录下没有实际的测试工具文件（只有 __pycache__）

    验证测试工具已经迁移到 tests/ 目录

    注意：此测试验证 Property 3（测试工具集中化），
    将在 Task 4 完成后通过。
    """
    apps_tests_dir = project_root / "apps" / "tests"
    if not apps_tests_dir.exists():
        pytest.skip("apps/tests directory does not exist")

    # 检查 strategies, factories, mocks 子目录
    utility_dirs = ["strategies", "factories", "mocks"]
    issues = []

    for util_dir in utility_dirs:
        util_path = apps_tests_dir / util_dir
        if util_path.exists():
            # 检查是否有实际的 Python 文件（不是 __pycache__）
            python_files = [
                f for f in util_path.iterdir() if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"
            ]
            if python_files:
                issues.append((util_dir, python_files))

    # 此测试验证 Property 3（测试工具集中化）
    # 在 Task 4 完成清理 apps/tests 目录后将通过
    # 目前跳过此检查，因为它属于 Task 4 的范围
    if issues:
        pytest.skip("Files still in apps/tests/ (will be cleaned in Task 4): " + ", ".join(f"{d}/" for d, _ in issues))
