#!/usr/bin/env python3
"""批量修复core/config模块的简单类型错误 - 改进版"""

import re
from pathlib import Path
from typing import Tuple

def fix_optional_dict_params(content: str) -> Tuple[str, int]:
    """修复 config: Dict[str, Any] = None 为 config: Optional[Dict[str, Any]] = None"""
    count = 0
    
    # 更精确的模式 - 只匹配参数名为 config 的情况
    pattern = r'(\bconfig):\s*Dict\[str,\s*Any\]\s*=\s*None'
    
    if re.search(pattern, content):
        # 确保导入 Optional
        if 'from typing import' in content:
            # 检查是否已经导入 Optional
            import_match = re.search(r'from typing import ([^\n]+)', content)
            if import_match:
                imports = import_match.group(1)
                if 'Optional' not in imports:
                    # 添加 Optional 到现有导入
                    new_imports = imports.rstrip() + ', Optional'
                    content = content.replace(
                        f'from typing import {imports}',
                        f'from typing import {new_imports}'
                    )
        
        # 替换所有匹配
        new_content = re.sub(pattern, r'\1: Optional[Dict[str, Any]] = None', content)
        count = len(re.findall(pattern, content))
        content = new_content
    
    return content, count

def fix_missing_return_types(content: str) -> Tuple[str, int]:
    """为 __post_init__ 添加 -> None"""
    count = 0
    
    # 只匹配 __post_init__ 方法
    pattern = r'(def __post_init__\(self\)):\s*\n'
    
    if re.search(pattern, content):
        content = re.sub(pattern, r'\1 -> None:\n', content)
        count = 1
    
    return content, count

def fix_generic_types(content: str) -> Tuple[str, int]:
    """修复泛型类型参数缺失"""
    count = 0
    
    # 修复 deque 类型 - 更精确的模式
    pattern = r'(self\._\w+):\s*deque\s*=\s*deque'
    matches = list(re.finditer(pattern, content))
    if matches:
        # 确保导入 Any
        if 'from typing import' in content and ', Any' not in content and 'Any,' not in content:
            content = re.sub(
                r'(from typing import [^\n]+)',
                r'\1, Any',
                content,
                count=1
            )
        
        for match in reversed(matches):
            var_name = match.group(1)
            start, end = match.span()
            content = content[:start] + f'{var_name}: deque[Any] = deque' + content[end:]
            count += 1
    
    # 修复 Callable 类型（函数参数）
    pattern = r'(\w+):\s*Callable\s*\)'
    matches = list(re.finditer(pattern, content))
    if matches:
        for match in reversed(matches):
            param_name = match.group(1)
            start, end = match.span()
            content = content[:start] + f'{param_name}: Callable[..., Any])' + content[end:]
            count += 1
    
    return content, count

def fix_var_annotations(content: str, filename: str) -> Tuple[str, int]:
    """修复变量类型注解缺失"""
    count = 0
    
    # 针对特定文件的特定修复
    replacements = []
    
    if 'dependency_validator.py' in filename:
        replacements.append((r'(\s+)(path = \[\])', r'\1path: list[str] = []'))
    
    if 'registry.py' in filename:
        replacements.append((r'(\s+)(env_vars = \{\})', r'\1env_vars: dict[str, Any] = {}'))
    
    if 'steering_performance_monitor.py' in filename:
        replacements.append((r'(\s+)(_analysis_cache = \{\})', r'\1_analysis_cache: dict[str, Any] = {}'))
    
    if 'steering_cache_strategies.py' in filename:
        replacements.append((r'(\s+)(self\.recent_hits = \[\])', r'\1self.recent_hits: list[Any] = []'))
    
    # 通用修复
    replacements.extend([
        (r'(\s+)(levels = \{\})', r'\1levels: dict[str, int] = {}'),
        (r'(\s+)(metadata_dict = \{\})', r'\1metadata_dict: dict[str, Any] = {}'),
        (r'(\s+)(nested = \{\})', r'\1nested: dict[str, Any] = {}'),
        (r'(\s+)(snapshots = \[\])', r'\1snapshots: list[Any] = []'),
        (r'(\s+)(self\._cache = \{\})', r'\1self._cache: dict[str, Any] = {}'),
        (r'(\s+)(self\._access_times = \{\})', r'\1self._access_times: dict[str, float] = {}'),
        (r'(\s+)(self\._metrics = \{\})', r'\1self._metrics: dict[str, Any] = {}'),
        (r'(\s+)(self\._dependency_graph = \{\})', r'\1self._dependency_graph: dict[str, list[str]] = {}'),
        (r'(\s+)(cache_config = self\.)', r'\1cache_config: dict[str, Any] = self.'),
        (r'(\s+)(perf_config = self\.)', r'\1perf_config: dict[str, Any] = self.'),
        (r'(\s+)(dep_config = self\.)', r'\1dep_config: dict[str, Any] = self.'),
        (r'(\s+)(rules_config = self\.)', r'\1rules_config: list[Any] = self.'),
        (r'(\s+)(applicable_specs = \[\])', r'\1applicable_specs: list[str] = []'),
        (r'(\s+)(self\._file_pattern_cache = \{\})', r'\1self._file_pattern_cache: dict[str, list[str]] = {}'),
        (r'(\s+)(items = \[\])', r'\1items: list[Any] = []'),
        (r'(\s+)(result = \{\})', r'\1result: dict[str, Any] = {}'),
        (r'(\s+)(template_config = \{\})', r'\1template_config: dict[str, Any] = {}'),
        (r'(\s+)(dep_type_counts = defaultdict)', r'\1dep_type_counts: dict[str, int] = defaultdict'),
        (r'(\s+)(graph_data = \{)', r'\1graph_data: dict[str, Any] = {'),
    ])
    
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            count += 1
            content = new_content
    
    return content, count

def process_file(file_path: Path) -> dict[str, int]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        stats = {
            'optional_params': 0,
            'return_types': 0,
            'generic_types': 0,
            'var_annotations': 0
        }
        
        # 应用所有修复
        content, count = fix_optional_dict_params(content)
        stats['optional_params'] = count
        
        content, count = fix_missing_return_types(content)
        stats['return_types'] = count
        
        content, count = fix_generic_types(content)
        stats['generic_types'] = count
        
        content, count = fix_var_annotations(content, file_path.name)
        stats['var_annotations'] = count
        
        # 只有在内容改变时才写入
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            return stats
        
        return {}
        
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return {}

def main() -> None:
    """主函数"""
    base_path = Path(__file__).parent.parent / 'apps' / 'core' / 'config'
    
    if not base_path.exists():
        print(f"错误: 路径不存在 {base_path}")
        return
    
    # 获取所有Python文件
    py_files = list(base_path.rglob('*.py'))
    
    print(f"找到 {len(py_files)} 个Python文件")
    
    total_stats = {
        'files_modified': 0,
        'optional_params': 0,
        'return_types': 0,
        'generic_types': 0,
        'var_annotations': 0
    }
    
    for py_file in py_files:
        stats = process_file(py_file)
        if stats:
            total_stats['files_modified'] += 1
            for key in ['optional_params', 'return_types', 'generic_types', 'var_annotations']:
                total_stats[key] += stats.get(key, 0)
            
            if sum(stats.values()) > 0:
                print(f"✓ {py_file.relative_to(base_path)}: {stats}")
    
    print("\n修复统计:")
    print(f"  修改文件数: {total_stats['files_modified']}")
    print(f"  Optional参数修复: {total_stats['optional_params']}")
    print(f"  返回类型修复: {total_stats['return_types']}")
    print(f"  泛型类型修复: {total_stats['generic_types']}")
    print(f"  变量注解修复: {total_stats['var_annotations']}")
    print(f"  总修复数: {sum(v for k, v in total_stats.items() if k != 'files_modified')}")

if __name__ == '__main__':
    main()
