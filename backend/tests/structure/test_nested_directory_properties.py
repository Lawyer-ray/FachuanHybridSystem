"""
Property-Based Tests for Nested Directory Detection

测试项目中不存在嵌套的重复目录结构

**Feature: backend-cleanup-optimization, Property 2: 无嵌套目录结构**
**Validates: Requirements 2.3**
"""

import pytest
from apps.core.path import Path
from hypothesis import given, strategies as st, assume, settings
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def find_all_directories(root: Path, max_depth: int = 10) -> list[Path]:
    """递归查找所有目录"""
    directories = []
    
    def _find_dirs(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for item in path.iterdir():
                if item.is_dir():
                    # 跳过隐藏目录和缓存目录
                    if item.name.startswith('.') or item.name in {
                        '__pycache__', 'node_modules', 'venv', 'venv311', 'venv312',
                        '.venv', 'htmlcov', '.hypothesis', '.mypy_cache',
                        '.pytest_cache', '.git', '.idea', '.vscode'
                    }:
                        continue
                    directories.append(item)
                    _find_dirs(item, depth + 1)
        except PermissionError:
            pass
    
    _find_dirs(root, 0)
    return directories


def is_nested_duplicate(dir_path: Path) -> tuple[bool, str]:
    """
    检查目录是否是嵌套的重复结构
    
    例如: tests/admin/backend/tests/admin/ 是 tests/admin/ 的嵌套重复
    
    Returns:
        tuple[bool, str]: (是否是嵌套重复, 描述信息)
    """
    parts = dir_path.parts
    
    # 查找 'backend' 在路径中的位置
    # 如果 'backend' 出现在非根目录位置，可能是嵌套
    for i, part in enumerate(parts):
        if part == 'backend' and i > 0:
            # 检查 backend 之后的路径是否与之前的路径重复
            # 例如: /root/tests/admin/backend/tests/admin
            # parts[i+1:] = ['tests', 'admin']
            # 检查这是否与 parts[:i] 中的某个子序列匹配
            after_backend = parts[i+1:]
            before_backend = parts[:i]
            
            # 检查 after_backend 是否是 before_backend 的后缀
            if len(after_backend) > 0:
                for j in range(len(before_backend)):
                    suffix = before_backend[j:]
                    if len(suffix) >= len(after_backend):
                        if suffix[:len(after_backend)] == after_backend:
                            return True, f"Nested duplicate: {dir_path} duplicates {Path(*before_backend)}"
    
    return False, ""


def check_for_nested_backend_directories(root: Path) -> list[str]:
    """
    检查项目中是否存在嵌套的 backend 目录
    
    Returns:
        list[str]: 发现的嵌套目录问题列表
    """
    issues = []
    
    # 查找所有名为 'backend' 的目录（不在根目录）
    for item in root.rglob('backend'):
        if item.is_dir():
            # 获取相对路径
            rel_path = item.relative_to(root)
            
            # 如果 backend 不是根目录的直接子目录，则可能是嵌套
            if len(rel_path.parts) > 1:
                # 检查这个 backend 目录下是否有与父目录相似的结构
                parent_parts = rel_path.parts[:-1]  # 去掉 'backend'
                
                # 检查 backend 目录下是否有重复的目录结构
                for sub_item in item.rglob('*'):
                    if sub_item.is_dir():
                        sub_rel = sub_item.relative_to(item)
                        # 检查是否与父路径匹配
                        if len(sub_rel.parts) > 0:
                            for i in range(len(parent_parts)):
                                if parent_parts[i:] == sub_rel.parts[:len(parent_parts)-i]:
                                    issues.append(
                                        f"Nested directory structure found: {sub_item.relative_to(root)}"
                                    )
                                    break
    
    return issues


# 获取所有目录用于测试
all_directories = find_all_directories(project_root)
if all_directories:
    directory_strategy = st.sampled_from(all_directories)
else:
    # 如果没有目录，创建一个空策略
    directory_strategy = st.just(project_root)


@given(directory_strategy)
@settings(max_examples=20, deadline=None)
def test_no_nested_directory_structures_property(dir_path: Path):
    """
    Property 2: 无嵌套目录结构
    
    *For any* directory in the project, it should not contain a nested copy 
    of itself (e.g., `tests/admin/backend/tests/admin/` is invalid).
    
    **Feature: backend-cleanup-optimization, Property 2: 无嵌套目录结构**
    **Validates: Requirements 2.3**
    """
    assume(dir_path.exists())
    
    is_nested, description = is_nested_duplicate(dir_path)
    
    assert not is_nested, (
        f"Nested directory structure detected:\n"
        f"  Path: {dir_path}\n"
        f"  Issue: {description}\n"
        f"\nNested directory structures should be removed to maintain a clean project hierarchy."
    )


def test_no_backend_directory_inside_tests():
    """
    测试 tests 目录下不存在 backend 子目录
    
    验证 tests/admin/backend/ 这样的嵌套结构不存在
    """
    tests_dir = project_root / 'tests'
    if not tests_dir.exists():
        pytest.skip("tests directory does not exist")
    
    # 查找 tests 目录下所有名为 'backend' 的目录
    nested_backends = list(tests_dir.rglob('backend'))
    nested_backends = [p for p in nested_backends if p.is_dir()]
    
    assert len(nested_backends) == 0, (
        f"Found nested 'backend' directories inside tests/:\n" +
        "\n".join(f"  - {p.relative_to(project_root)}" for p in nested_backends) +
        "\n\nThese nested directories should be removed."
    )


def test_no_nested_duplicate_structures():
    """
    测试项目中不存在嵌套的重复目录结构
    
    验证没有类似 tests/admin/backend/tests/admin/ 的结构
    """
    issues = check_for_nested_backend_directories(project_root)
    
    assert len(issues) == 0, (
        f"Found nested duplicate directory structures:\n" +
        "\n".join(f"  - {issue}" for issue in issues) +
        "\n\nThese nested structures should be removed."
    )


def test_directory_depth_reasonable():
    """
    测试目录深度合理
    
    验证没有过深的目录嵌套（超过 8 层）
    """
    max_allowed_depth = 8
    deep_directories = []
    
    for dir_path in all_directories:
        try:
            rel_path = dir_path.relative_to(project_root)
            depth = len(rel_path.parts)
            if depth > max_allowed_depth:
                deep_directories.append((dir_path, depth))
        except ValueError:
            pass
    
    assert len(deep_directories) == 0, (
        f"Found directories with excessive depth (>{max_allowed_depth}):\n" +
        "\n".join(f"  - {p.relative_to(project_root)} (depth: {d})" for p, d in deep_directories) +
        "\n\nConsider flattening the directory structure."
    )


def test_no_duplicate_directory_names_in_path():
    """
    测试路径中没有重复的目录名
    
    验证没有类似 admin/admin/ 或 tests/tests/ 的结构
    """
    # 允许的重复目录名（Django 项目结构）
    allowed_duplicates = {
        'apiSystem/apiSystem',  # Django 项目结构：项目名/项目名
    }
    
    duplicates = []
    
    for dir_path in all_directories:
        try:
            rel_path = dir_path.relative_to(project_root)
            parts = rel_path.parts
            
            # 检查连续重复
            for i in range(len(parts) - 1):
                if parts[i] == parts[i + 1]:
                    # 检查是否在允许列表中
                    rel_str = str(rel_path)
                    if rel_str not in allowed_duplicates:
                        duplicates.append(dir_path)
                    break
        except ValueError:
            pass
    
    assert len(duplicates) == 0, (
        f"Found directories with duplicate names in path:\n" +
        "\n".join(f"  - {p.relative_to(project_root)}" for p in duplicates) +
        "\n\nThese duplicate structures should be cleaned up."
    )
