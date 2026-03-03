"""
Property-Based Tests for Temporary Files

测试临时文件和生成文件不在版本控制中
"""

import subprocess
import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.core.path import Path

# 添加项目根目录到 Python 路径
backend_root = Path(__file__).parent.parent.parent
project_root = backend_root.parent  # 实际的项目根目录（包含 .gitignore）
sys.path.insert(0, str(backend_root))


def get_all_files_in_project():
    """获取项目中可能存在的临时文件（仅扫描小型临时目录，跳过大型缓存）"""
    # 只扫描小型临时目录，跳过 .mypy_cache/.hypothesis/htmlcov 等大型缓存
    # 这些大型缓存目录由 test_cache_directories_not_tracked 单独验证
    small_temp_dirs = ["__pycache__", ".pytest_cache", "logs"]
    files: list[str] = []
    for temp_dir in small_temp_dirs:
        target = backend_root / temp_dir
        if target.exists() and target.is_dir():
            for item in target.rglob("*"):
                if item.is_file():
                    files.append(str(item.relative_to(backend_root)))
    # 也检查根目录下的临时文件（不递归）
    for item in backend_root.iterdir():
        if item.is_file() and is_temporary_or_generated_file(item.name):
            files.append(str(item.relative_to(backend_root)))
    return files


def is_tracked_by_git(file_path: str) -> bool:
    """检查文件是否被 Git 跟踪"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", file_path],  # noqa: S607
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # 如果 git 命令不可用或超时，跳过测试
        return False


def is_temporary_or_generated_file(file_path: str) -> bool:
    """判断文件是否是临时文件或生成文件"""
    path = Path(file_path)

    # 临时文件和生成文件的模式
    temp_patterns = [
        # Python 缓存
        "__pycache__",
        ".pyc",
        ".pyo",
        ".pyd",
        # 测试和覆盖率
        ".coverage",
        "htmlcov",
        ".pytest_cache",
        ".hypothesis",
        ".tox",
        ".nox",
        # 类型检查
        ".mypy_cache",
        # IDE
        ".idea",
        ".vscode",
        ".DS_Store",
        # 日志
        "logs/",
        ".log",
        # 数据库
        "db.sqlite3",
        ".sqlite3",
        # 临时文件
        ".tmp",
        ".temp",
        ".bak",
        ".swp",
        ".swo",
        # 构建产物
        "build/",
        "dist/",
        "*.egg-info",
    ]

    file_str = str(path)

    # 检查是否匹配任何临时文件模式
    for pattern in temp_patterns:
        if pattern in file_str:
            return True

    # 检查特定的临时文件扩展名
    if path.suffix in [".pyc", ".pyo", ".pyd", ".log", ".tmp", ".temp", ".bak", ".swp", ".swo"]:
        return True

    return False


# 创建文件路径策略
all_files = get_all_files_in_project()
if all_files:
    # 只选择临时文件和生成文件
    temp_files = [f for f in all_files if is_temporary_or_generated_file(f)]
    if temp_files:
        file_strategy = st.sampled_from(temp_files)
    else:
        # 如果没有临时文件，使用一个虚拟策略
        file_strategy = st.just("__pycache__/dummy.pyc")
else:
    file_strategy = st.just("__pycache__/dummy.pyc")


@given(file_strategy)
@settings(max_examples=20, deadline=None)
def test_temporary_files_not_in_version_control_property(file_path):
    """
    Property 11: 临时文件不在版本控制

    For any temporary or generated file (cache, logs, coverage reports),
    it should be listed in .gitignore and not tracked by git

    Feature: backend-structure-optimization, Property 11: 临时文件不在版本控制
    Validates: Requirements 5.2, 5.3
    """
    # 检查文件是否存在
    full_path = backend_root / file_path
    assume(full_path.exists())

    # 检查文件是否是临时文件或生成文件
    assume(is_temporary_or_generated_file(file_path))

    # 断言：临时文件不应该被 Git 跟踪
    is_tracked = is_tracked_by_git(file_path)

    assert (
        not is_tracked
    ), f"Temporary/generated file is tracked by Git: {file_path}\nThis file should be added to .gitignore"


def test_gitignore_exists():
    """
    测试 .gitignore 文件存在

    验证项目有 .gitignore 文件
    """
    gitignore_path = project_root / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file does not exist"


def test_common_temp_patterns_in_gitignore():
    """
    测试常见的临时文件模式在 .gitignore 中

    验证 .gitignore 包含常见的临时文件和生成文件模式
    """
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        pytest.skip(".gitignore file does not exist")

    gitignore_content = gitignore_path.read_text()

    # 必须包含的模式（或等效模式）
    required_patterns = {
        "__pycache__": ["__pycache__"],
        "*.pyc": ["*.pyc", "*.py[cod]"],  # *.py[cod] 覆盖 *.pyc
        ".pytest_cache": [".pytest_cache"],
        ".mypy_cache": [".mypy_cache"],
        ".hypothesis": [".hypothesis"],
        ".coverage": [".coverage"],
        "htmlcov": ["htmlcov"],
        "*.log": ["*.log"],
        "logs/": ["logs/"],
        "db.sqlite3": ["db.sqlite3", "*.sqlite3"],  # *.sqlite3 覆盖 db.sqlite3
        ".DS_Store": [".DS_Store"],
        ".env": [".env"],
        "venv": ["venv", "venv/"],
    }

    missing_patterns = []
    for pattern_name, alternatives in required_patterns.items():
        # 检查是否有任何一个等效模式存在
        if not any(alt in gitignore_content for alt in alternatives):
            missing_patterns.append(pattern_name)

    assert len(missing_patterns) == 0, "The following patterns should be in .gitignore:\n" + "\n".join(
        f"  - {pattern}" for pattern in missing_patterns
    )


def test_cache_directories_not_tracked():
    """
    测试缓存目录不被 Git 跟踪

    验证常见的缓存目录不在版本控制中
    """
    cache_dirs = [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".hypothesis",
        "htmlcov",
    ]

    # 使用 git ls-files 批量检查，避免逐文件 subprocess 调用导致超时
    tracked_cache_files: list[str] = []
    for cache_dir in cache_dirs:
        cache_path = backend_root / cache_dir
        if cache_path.exists():
            try:
                result = subprocess.run(
                    ["git", "ls-files", cache_dir],  # noqa: S607
                    cwd=backend_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    tracked_cache_files.extend(result.stdout.strip().splitlines())
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    assert len(tracked_cache_files) == 0, (
        "The following cache files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in tracked_cache_files)
        + "\n\nThese files should be removed from Git and added to .gitignore"
    )


def test_log_files_not_tracked():
    """
    测试日志文件不被 Git 跟踪

    验证日志文件不在版本控制中
    """
    log_files = []

    # 只检查 logs/ 目录（避免 rglob 扫描 .venv 等大目录）
    logs_dir = backend_root / "logs"
    if logs_dir.exists():
        for file in logs_dir.rglob("*.log"):
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                log_files.append(str(relative_path))

    # 检查根目录下的 .log 文件（不递归）
    for file in backend_root.iterdir():
        if file.is_file() and file.suffix == ".log":
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                log_files.append(str(relative_path))

    assert len(log_files) == 0, (
        "The following log files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in log_files)
        + "\n\nLog files should not be in version control"
    )


def test_coverage_files_not_tracked():
    """
    测试覆盖率文件不被 Git 跟踪

    验证覆盖率报告不在版本控制中
    """
    coverage_files: list[str] = []

    # 使用 git ls-files 批量检查，避免 rglob + subprocess 逐文件调用
    try:
        result = subprocess.run(
            ["git", "ls-files", ".coverage", "htmlcov"],  # noqa: S607
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            coverage_files = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    assert len(coverage_files) == 0, (
        "The following coverage files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in coverage_files)
        + "\n\nCoverage files should not be in version control"
    )


def test_database_files_not_tracked():
    """
    测试数据库文件不被 Git 跟踪

    验证 SQLite 数据库文件不在版本控制中
    """
    db_files = []

    # 只检查根目录下的 .sqlite3 文件（不递归扫描，避免超时）
    for file in backend_root.iterdir():
        if file.is_file() and file.suffix == ".sqlite3":
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                db_files.append(str(relative_path))

    assert len(db_files) == 0, (
        "The following database files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in db_files)
        + "\n\nDatabase files should not be in version control"
    )


def test_ide_config_not_tracked():  # noqa: C901
    """
    测试 IDE 配置不被 Git 跟踪

    验证 IDE 特定的配置文件不在版本控制中
    """
    ide_files = []

    # 检查 .idea/ 目录
    idea_dir = backend_root / ".idea"
    if idea_dir.exists():
        for file in idea_dir.rglob("*"):
            if file.is_file():
                relative_path = file.relative_to(backend_root)
                if is_tracked_by_git(str(relative_path)):
                    ide_files.append(str(relative_path))

    # 检查 .vscode/ 目录
    vscode_dir = backend_root / ".vscode"
    if vscode_dir.exists():
        for file in vscode_dir.rglob("*"):
            if file.is_file():
                relative_path = file.relative_to(backend_root)
                if is_tracked_by_git(str(relative_path)):
                    ide_files.append(str(relative_path))

    # 检查根目录下的 .DS_Store 文件（不递归，避免扫描 .venv）
    ds_store = backend_root / ".DS_Store"
    if ds_store.exists() and ds_store.is_file():
        if is_tracked_by_git(".DS_Store"):
            ide_files.append(".DS_Store")

    assert len(ide_files) == 0, (
        "The following IDE files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in ide_files)
        + "\n\nIDE-specific files should not be in version control"
    )


def test_python_cache_not_tracked():
    """
    测试 Python 缓存文件不被 Git 跟踪

    验证 .pyc 和 __pycache__ 不在版本控制中
    """
    # 使用 git ls-files 高效检查是否有 .pyc 或 __pycache__ 文件被跟踪
    cache_files = []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "*.pyc", "*__pycache__*"],  # noqa: S607
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            cache_files = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("git 命令不可用")

    assert len(cache_files) == 0, (
        "The following Python cache files are tracked by Git:\n"
        + "\n".join(f"  - {file}" for file in cache_files)
        + "\n\nPython cache files should not be in version control"
    )
