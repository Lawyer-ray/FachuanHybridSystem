#!/usr/bin/env python3
"""
修复 core/config 模块的类型错误
"""
import re
from pathlib import Path
from typing import Any


def fix_deque_types(file_path: Path) -> bool:
    """修复 deque 泛型类型参数缺失"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 deque 类型注解
    content = re.sub(
        r': deque = deque\(maxlen=',
        r': deque[dict[str, Any]] = deque(maxlen=',
        content
    )
    
    # 确保导入了 deque 和 Any
    if 'from collections import deque' in content and 'deque[' in content:
        if 'from typing import' in content and 'Any' not in content:
            content = re.sub(
                r'from typing import ([^)]+)',
                r'from typing import \1, Any',
                content,
                count=1
            )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_dict_annotations(file_path: Path) -> bool:
    """修复字典类型注解缺失"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 Need type annotation for "xxx" 错误
    # 查找 self.xxx = {} 模式
    patterns = [
        (r'(\s+)(self\._cache) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(self\._analysis_cache) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(self\._file_pattern_cache) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(self\._access_times) = \{\}', r'\1\2: dict[str, float] = {}'),
        (r'(\s+)(self\._metrics) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(self\._dependency_graph) = \{\}', r'\1\2: dict[str, list[str]] = {}'),
        (r'(\s+)(self\.recent_hits) = \[\]', r'\1\2: list[Any] = []'),
        (r'(\s+)(levels) = \{\}', r'\1\2: dict[str, int] = {}'),
        (r'(\s+)(metadata_dict) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(graph_data) = \{', r'\1\2: dict[str, Any] = {'),
        (r'(\s+)(dep_type_counts) = defaultdict\(int\)', r'\1\2: dict[str, int] = defaultdict(int)'),
        (r'(\s+)(items) = \[\]', r'\1\2: list[Any] = []'),
        (r'(\s+)(result) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(template_config) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(nested) = \{\}', r'\1\2: dict[str, Any] = {}'),
        (r'(\s+)(snapshots) = \[\]', r'\1\2: list[Any] = []'),
        (r'(\s+)(rules_config) = self\.config_manager\.get\(', r'\1\2: list[Any] = self.config_manager.get('),
        (r'(\s+)(applicable_specs) = \[\]', r'\1\2: list[str] = []'),
        (r'(\s+)(cache_config) = self\.config_manager\.get\(', r'\1\2: dict[str, Any] = self.config_manager.get('),
        (r'(\s+)(perf_config) = self\.config_manager\.get\(', r'\1\2: dict[str, Any] = self.config_manager.get('),
        (r'(\s+)(dep_config) = self\.config_manager\.get\(', r'\1\2: dict[str, Any] = self.config_manager.get('),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    # 确保导入了 Any
    if ': dict[str, Any]' in content or ': list[Any]' in content:
        if 'from typing import' in content and 'Any' not in content:
            content = re.sub(
                r'from typing import ([^)]+)',
                r'from typing import \1, Any',
                content,
                count=1
            )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_callable_types(file_path: Path) -> bool:
    """修复 Callable 泛型类型参数缺失"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 Callable 类型注解
    content = re.sub(
        r'loading_func: Callable\)',
        r'loading_func: Callable[..., Any])',
        content
    )
    content = re.sub(
        r'loader_func: Callable\)',
        r'loader_func: Callable[..., Any])',
        content
    )
    
    # 确保导入了 Callable
    if 'Callable[' in content:
        if 'from typing import' in content and 'Callable' not in content:
            content = re.sub(
                r'from typing import ([^)]+)',
                r'from typing import \1, Callable',
                content,
                count=1
            )
        elif 'from typing import' not in content and 'from collections.abc import' not in content:
            # 在文件开头添加导入
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('from ') or line.startswith('import '):
                    lines.insert(i, 'from typing import Callable, Any')
                    break
            content = '\n'.join(lines)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_set_types(file_path: Path) -> bool:
    """修复 set 泛型类型参数缺失"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 set 返回类型
    content = re.sub(
        r'-> set:',
        r'-> set[Any]:',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_optional_defaults(file_path: Path) -> bool:
    """修复可选参数默认值类型不匹配"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 fallback_settings_key: str = None
    content = re.sub(
        r'fallback_settings_key: str = None',
        r'fallback_settings_key: str | None = None',
        content
    )
    
    # 修复 default: T = None
    content = re.sub(
        r'default: T = None\)',
        r'default: T | None = None)',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def fix_cast_any_returns(file_path: Path) -> bool:
    """使用 cast() 修复 Returning Any 错误"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 确保导入了 cast
    if 'from typing import' in content and 'cast' not in content:
        content = re.sub(
            r'from typing import ([^)]+)',
            r'from typing import \1, cast',
            content,
            count=1
        )
    elif 'from typing import' not in content:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                lines.insert(i, 'from typing import cast')
                break
        content = '\n'.join(lines)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    config_path = backend_path / 'apps' / 'core' / 'config'
    
    fixed_files = 0
    
    for py_file in config_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        fixed = False
        fixed = fix_deque_types(py_file) or fixed
        fixed = fix_dict_annotations(py_file) or fixed
        fixed = fix_callable_types(py_file) or fixed
        fixed = fix_set_types(py_file) or fixed
        fixed = fix_optional_defaults(py_file) or fixed
        fixed = fix_cast_any_returns(py_file) or fixed
        
        if fixed:
            fixed_files += 1
            print(f"Fixed: {py_file.relative_to(backend_path)}")
    
    print(f"\n总共修复了 {fixed_files} 个文件")


if __name__ == '__main__':
    main()
