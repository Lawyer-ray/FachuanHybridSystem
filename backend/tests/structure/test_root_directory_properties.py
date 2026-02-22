"""
Property-Based Tests for Root Directory Structure

测试根目录结构的简洁性
"""

import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.refactoring.structure_validator import ProjectStructureValidator

# 根目录允许的文件（根据 design.md 中的 CleanupConfig）
ALLOWED_ROOT_FILES = {
    "README.md",
    "Makefile",
    "pytest.ini",
    "mypy.ini",
    "pyproject.toml",
    "ruff.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "conftest.py",
    ".dockerignore",
    ".env.example",
    ".env",
    ".env.dev",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".secrets.baseline",
    ".coverage",
    ".DS_Store",
    # uv 包管理器的锁文件，项目使用 uv 替代 pip
    "uv.lock",
}

# 根目录允许的目录
ALLOWED_ROOT_DIRS = {
    "apiSystem",
    "apps",
    "tests",
    "scripts",
    "docs",
    "deploy",
    "logs",
    "htmlcov",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".git",
    ".idea",
    ".vscode",
    ".trae",
    ".kiro",
    ".ruff_cache",
    "venv311",
    "venv312",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    "media",
    "constraints",
    "devtools",
    "tests_smoke",
    ".env.dev",
}

# 临时文件模式（不应该存在于根目录）
TEMP_FILE_PATTERNS = [
    "TASK*_COMPLETE.md",
    "*_SUMMARY.md",
    "*_VERIFICATION_REPORT.md",
]


def get_root_items():
    """获取根目录中的所有项目"""
    items = []
    for item in project_root.iterdir():
        items.append(item.name)
    return items


def matches_temp_pattern(filename: str) -> bool:
    """检查文件名是否匹配临时文件模式"""
    import fnmatch

    for pattern in TEMP_FILE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


# 创建根目录项目策略
root_items = get_root_items()
if root_items:
    root_item_strategy = st.sampled_from(root_items)
else:
    root_item_strategy = st.text(min_size=1, max_size=50)


@given(root_item_strategy)
@settings(max_examples=20, deadline=None)
def test_root_directory_cleanliness_property(item_name):
    """
    Property 1: 根目录清洁性

    *For any* file in the Backend root directory after cleanup, it should
    either be in the allowed files list or be a directory in the allowed
    directories list.

    Feature: backend-cleanup-optimization, Property 1: 根目录清洁性
    **Validates: Requirements 1.1**
    """
    # 检查项目是否存在
    item_path = project_root / item_name
    assume(item_path.exists())

    if item_path.is_dir():
        # 目录应该在允许的目录列表中
        assert item_name in ALLOWED_ROOT_DIRS, (
            f"Unexpected directory in root: {item_name}\n"
            f"Root directory should only contain allowed directories.\n"
            f"Allowed directories: {sorted(ALLOWED_ROOT_DIRS)}"
        )
    else:
        # 文件应该在允许的文件列表中
        assert item_name in ALLOWED_ROOT_FILES, (
            f"Unexpected file in root: {item_name}\n"
            f"Root directory should only contain allowed configuration files.\n"
            f"Allowed files: {sorted(ALLOWED_ROOT_FILES)}"
        )

        # 额外检查：不应该有临时文件
        assert not matches_temp_pattern(item_name), (
            f"Temporary file found in root: {item_name}\n"
            f"Temporary files matching patterns {TEMP_FILE_PATTERNS} should be removed or moved."
        )


@given(root_item_strategy)
@settings(max_examples=20, deadline=None)
def test_root_directory_simplicity_property(item_name):
    """
    Property 10: 根目录简洁性

    For any file or directory in the root directory, it should be in the
    whitelist of allowed items (configuration files, essential directories,
    and README.md)

    Feature: backend-structure-optimization, Property 10: 根目录简洁性
    Validates: Requirements 1.5, 8.1
    """
    # 检查项目是否存在
    item_path = project_root / item_name
    assume(item_path.exists())

    # 白名单：允许的文件和目录
    allowed_items = {
        # 核心目录
        "apiSystem",
        "apps",
        "tests",
        "scripts",
        "docs",
        "logs",
        # 缓存和生成目录
        ".hypothesis",
        ".mypy_cache",
        ".pytest_cache",
        "htmlcov",
        "__pycache__",
        # 配置文件
        ".env.example",
        ".env",
        ".env.dev",
        ".gitignore",
        ".pre-commit-config.yaml",
        "conftest.py",
        "pytest.ini",
        "mypy.ini",
        "pyproject.toml",
        "ruff.toml",
        "requirements.txt",
        "Makefile",
        "README.md",
        ".secrets.baseline",
        # 系统文件
        ".DS_Store",
        ".git",
        "venv311",
        "venv312",
        ".venv",
        "venv",
        # 临时文件（应该在 .gitignore 中）
        ".coverage",
        "IMPLEMENTATION_CHECKLIST.md",
        # IDE 配置
        ".idea",
        ".vscode",
        ".trae",
        ".kiro",
        # 缓存与运行时目录
        ".cache",
        ".ruff_cache",
        "media",
        # 遗留目录（待清理）
        "backend",
        # 遗留文档文件（待迁移到 docs/）
        "CODE_QUALITY_REVIEW.md",
        "DATA_RECOVERY_GUIDE.md",
        "PERFORMANCE_MONITORING_IMPLEMENTATION.md",
        "QUICK_START.md",
        "constraints",
        "devtools",
        "deploy",
        "tests_smoke",
        "requirements-dev.txt",
        "requirements-test.txt",
        ".dockerignore",
        # uv 包管理器的锁文件，项目使用 uv 替代 pip
        "uv.lock",
    }

    # 断言：项目应该在白名单中
    assert item_name in allowed_items, (
        f"Unexpected item in root directory: {item_name}\n"
        f"Root directory should only contain essential files and directories."
    )


def test_root_directory_has_required_directories():
    """
    测试根目录包含必需的目录

    验证根目录包含 apiSystem, apps, scripts
    """
    validator = ProjectStructureValidator(project_root)
    errors = validator.validate_root_directory()

    # 过滤出只关于缺失必需目录的错误
    missing_required = [error for error in errors if "Missing required directory" in error]

    assert len(missing_required) == 0, f"Root directory is missing required directories:\n" + "\n".join(
        f"  - {error}" for error in missing_required
    )


def test_root_directory_only_contains_allowed_items():
    """
    测试根目录只包含允许的项目

    验证根目录中没有意外的文件或目录
    """
    validator = ProjectStructureValidator(project_root)
    errors = validator.validate_root_directory()

    # 过滤出只关于意外项目的错误
    unexpected_items = [error for error in errors if "Unexpected item" in error]

    assert len(unexpected_items) == 0, f"Root directory contains unexpected items:\n" + "\n".join(
        f"  - {error}" for error in unexpected_items
    )


def test_root_directory_structure_complete():
    """
    测试根目录结构完整性

    验证根目录结构符合所有要求
    """
    validator = ProjectStructureValidator(project_root)
    errors = validator.validate_root_directory()

    assert len(errors) == 0, f"Root directory validation failed:\n" + "\n".join(f"  - {error}" for error in errors)


def test_essential_config_files_exist():
    """
    测试必需的配置文件存在

    验证根目录包含必需的配置文件
    """
    # backend/ 目录下必需的配置文件（requirements.txt 和 README.md 在项目根目录，不在 backend/）
    essential_files = ["pytest.ini", "Makefile"]

    missing_files = []
    for file_name in essential_files:
        file_path = project_root / file_name
        if not file_path.exists():
            missing_files.append(file_name)

    assert len(missing_files) == 0, f"Root directory is missing essential config files:\n" + "\n".join(
        f"  - {file}" for file in missing_files
    )


def test_no_markdown_files_in_root_except_readme():
    """
    测试根目录除了 README.md 外没有其他 Markdown 文件

    验证所有其他 Markdown 文档都移到了 docs/ 目录
    """
    markdown_files = []
    for item in project_root.iterdir():
        if item.is_file() and item.suffix == ".md" and item.name != "README.md":
            markdown_files.append(item.name)

    # 允许的例外（临时文件）
    allowed_exceptions = {"IMPLEMENTATION_CHECKLIST.md"}
    unexpected_markdown = [f for f in markdown_files if f not in allowed_exceptions]

    assert len(unexpected_markdown) == 0, (
        f"Root directory contains unexpected Markdown files:\n"
        + "\n".join(f"  - {file}" for file in unexpected_markdown)
        + "\n\nThese files should be moved to the docs/ directory."
    )


def test_no_python_files_in_root():
    """
    测试根目录没有 Python 源文件

    验证所有 Python 代码都在适当的模块中
    """
    python_files = []
    for item in project_root.iterdir():
        if item.is_file() and item.suffix == ".py" and item.name != "conftest.py":
            python_files.append(item.name)

    assert len(python_files) == 0, (
        f"Root directory contains unexpected Python files:\n"
        + "\n".join(f"  - {file}" for file in python_files)
        + "\n\nPython files should be in appropriate modules (apps/, scripts/, tests/)."
    )


def test_cache_directories_in_gitignore():
    """
    测试缓存目录在 .gitignore 中

    验证生成的目录和缓存文件不会被提交到版本控制
    """
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        pytest.skip(".gitignore file does not exist")

    gitignore_content = gitignore_path.read_text()

    # 应该被忽略的目录和文件
    should_be_ignored = ["__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis", "htmlcov", ".coverage"]

    missing_in_gitignore = []
    for pattern in should_be_ignored:
        if pattern not in gitignore_content:
            missing_in_gitignore.append(pattern)

    assert len(missing_in_gitignore) == 0, f"The following patterns should be in .gitignore:\n" + "\n".join(
        f"  - {pattern}" for pattern in missing_in_gitignore
    )
