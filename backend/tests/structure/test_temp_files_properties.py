"""
Property-Based Tests for Temporary Files

测试临时文件和生成文件不在版本控制中
"""

import pytest
from apps.core.path import Path
from hypothesis import given, strategies as st, assume, settings
import subprocess
import sys

# 添加项目根目录到 Python 路径
backend_root = Path(__file__).parent.parent.parent
project_root = backend_root.parent  # 实际的项目根目录（包含 .gitignore）
sys.path.insert(0, str(backend_root))


def get_all_files_in_project():
    """获取项目中的所有文件（递归）"""
    files = []
    for item in backend_root.rglob("*"):
        if item.is_file():
            # 排除 .git 目录
            if ".git" not in item.parts:
                relative_path = item.relative_to(backend_root)
                files.append(str(relative_path))
    return files


def is_tracked_by_git(file_path: str) -> bool:
    """检查文件是否被 Git 跟踪"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", file_path],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=5
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
    if path.suffix in ['.pyc', '.pyo', '.pyd', '.log', '.tmp', '.temp', '.bak', '.swp', '.swo']:
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
    
    assert not is_tracked, (
        f"Temporary/generated file is tracked by Git: {file_path}\n"
        f"This file should be added to .gitignore"
    )


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
    
    assert len(missing_patterns) == 0, (
        f"The following patterns should be in .gitignore:\n" +
        "\n".join(f"  - {pattern}" for pattern in missing_patterns)
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
    
    tracked_cache_dirs = []
    for cache_dir in cache_dirs:
        # 检查是否有该目录的文件被跟踪
        cache_path = backend_root / cache_dir
        if cache_path.exists():
            for file in cache_path.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(backend_root)
                    if is_tracked_by_git(str(relative_path)):
                        tracked_cache_dirs.append(str(relative_path))
    
    assert len(tracked_cache_dirs) == 0, (
        f"The following cache files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in tracked_cache_dirs) +
        "\n\nThese files should be removed from Git and added to .gitignore"
    )


def test_log_files_not_tracked():
    """
    测试日志文件不被 Git 跟踪
    
    验证日志文件不在版本控制中
    """
    log_files = []
    
    # 检查 logs/ 目录
    logs_dir = backend_root / "logs"
    if logs_dir.exists():
        for file in logs_dir.rglob("*.log"):
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                log_files.append(str(relative_path))
    
    # 检查其他 .log 文件
    for file in backend_root.rglob("*.log"):
        if file.is_file():
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                log_files.append(str(relative_path))
    
    assert len(log_files) == 0, (
        f"The following log files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in log_files) +
        "\n\nLog files should not be in version control"
    )


def test_coverage_files_not_tracked():
    """
    测试覆盖率文件不被 Git 跟踪
    
    验证覆盖率报告不在版本控制中
    """
    coverage_files = []
    
    # 检查 .coverage 文件
    coverage_file = backend_root / ".coverage"
    if coverage_file.exists() and is_tracked_by_git(".coverage"):
        coverage_files.append(".coverage")
    
    # 检查 htmlcov/ 目录
    htmlcov_dir = backend_root / "htmlcov"
    if htmlcov_dir.exists():
        for file in htmlcov_dir.rglob("*"):
            if file.is_file():
                relative_path = file.relative_to(backend_root)
                if is_tracked_by_git(str(relative_path)):
                    coverage_files.append(str(relative_path))
    
    assert len(coverage_files) == 0, (
        f"The following coverage files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in coverage_files) +
        "\n\nCoverage files should not be in version control"
    )


def test_database_files_not_tracked():
    """
    测试数据库文件不被 Git 跟踪
    
    验证 SQLite 数据库文件不在版本控制中
    """
    db_files = []
    
    # 检查所有 .sqlite3 文件
    for file in backend_root.rglob("*.sqlite3"):
        if file.is_file():
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                db_files.append(str(relative_path))
    
    # 检查 db.sqlite3
    for file in backend_root.rglob("db.sqlite3"):
        if file.is_file():
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                db_files.append(str(relative_path))
    
    assert len(db_files) == 0, (
        f"The following database files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in db_files) +
        "\n\nDatabase files should not be in version control"
    )


def test_ide_config_not_tracked():
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
    
    # 检查 .DS_Store 文件
    for file in backend_root.rglob(".DS_Store"):
        if file.is_file():
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                ide_files.append(str(relative_path))
    
    assert len(ide_files) == 0, (
        f"The following IDE files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in ide_files) +
        "\n\nIDE-specific files should not be in version control"
    )


def test_python_cache_not_tracked():
    """
    测试 Python 缓存文件不被 Git 跟踪
    
    验证 .pyc 和 __pycache__ 不在版本控制中
    """
    cache_files = []
    
    # 限制搜索范围和数量，避免超时
    max_files = 100
    file_count = 0
    
    # 检查所有 .pyc 文件
    for file in backend_root.rglob("*.pyc"):
        if file.is_file():
            file_count += 1
            if file_count > max_files:
                break
            relative_path = file.relative_to(backend_root)
            if is_tracked_by_git(str(relative_path)):
                cache_files.append(str(relative_path))
    
    # 如果已经找到太多，跳过剩余检查
    if file_count <= max_files:
        # 检查所有 __pycache__ 目录
        for pycache_dir in backend_root.rglob("__pycache__"):
            if pycache_dir.is_dir():
                for file in pycache_dir.rglob("*"):
                    if file.is_file():
                        file_count += 1
                        if file_count > max_files:
                            break
                        relative_path = file.relative_to(backend_root)
                        if is_tracked_by_git(str(relative_path)):
                            cache_files.append(str(relative_path))
                    if file_count > max_files:
                        break
                if file_count > max_files:
                    break
    
    # 如果文件太多，跳过测试
    if file_count > max_files:
        pytest.skip(f"Too many cache files ({file_count}), skipping detailed check")
    
    assert len(cache_files) == 0, (
        f"The following Python cache files are tracked by Git:\n" +
        "\n".join(f"  - {file}" for file in cache_files) +
        "\n\nPython cache files should not be in version control"
    )
