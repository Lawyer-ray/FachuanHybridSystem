#!/usr/bin/env python3
"""批量修复 scraper 模块的简单类型错误"""

import re
from pathlib import Path
from typing import Any

import logging

logger = logging.getLogger(__name__)


def fix_implicit_optional(content: str) -> str:
    """修复隐式 Optional 参数（= None 但类型不是 | None）"""
    # 匹配模式：参数名: 类型 = None，但类型中没有 | None 或 Optional
    pattern = r'(\w+):\s*([^=\n]+?)\s*=\s*None'
    
    def replace_func(match: re.Match[str]) -> str:
        param_name = match.group(1)
        param_type = match.group(2).strip()
        
        # 如果已经有 | None 或 Optional，不修改
        if '| None' in param_type or 'Optional[' in param_type or 'None' in param_type:
            return match.group(0)
        
        # 添加 | None
        return f'{param_name}: {param_type} | None = None'
    
    return re.sub(pattern, replace_func, content)


def fix_any_lowercase(content: str) -> str:
    """修复 any -> Any"""
    # 只替换类型注解中的 any，不替换变量名
    content = re.sub(r'\bany\b(?=\s*[,\]\)])', 'Any', content)
    return content


def fix_missing_return_types(content: str) -> str:
    """为缺少返回类型的函数添加 -> None"""
    lines = content.split('\n')
    result_lines = []
    
    for i, line in enumerate(lines):
        # 匹配函数定义但没有返回类型注解
        if re.match(r'\s*def\s+\w+\s*\([^)]*\)\s*:', line):
            # 检查是否已有返回类型
            if '->' not in line:
                # 在 : 前添加 -> None
                line = line.replace('):', ') -> None:')
        
        result_lines.append(line)
    
    return '\n'.join(result_lines)


def fix_object_type_inference(content: str) -> str:
    """修复 object 类型推断问题（result = {} 导致的）"""
    # 查找 result = {"logs": [], ...} 这样的模式
    pattern = r'(\s+)(result)\s*=\s*\{([^}]+)\}'
    
    def replace_func(match: re.Match[str]) -> str:
        indent = match.group(1)
        var_name = match.group(2)
        content_str = match.group(3)
        
        # 检查是否包含 "logs": []
        if '"logs"' in content_str or "'logs'" in content_str:
            # 添加类型注解
            return f'{indent}{var_name}: dict[str, Any] = {{{content_str}}}'
        
        return match.group(0)
    
    return re.sub(pattern, replace_func, content)


def fix_tuple_type_params(content: str) -> str:
    """修复 tuple 缺少类型参数"""
    # -> tuple: 改为 -> tuple[Any, ...]
    content = re.sub(r'->\s*tuple\s*:', r'-> tuple[Any, ...]:',content)
    return content


def ensure_any_import(content: str) -> bool:
    """确保导入了 Any，返回是否需要添加导入"""
    # 检查是否使用了 Any
    if 'Any' not in content:
        return False
    
    # 检查是否已导入 Any
    if re.search(r'from typing import.*\bAny\b', content):
        return False
    
    return True


def add_any_import(content: str) -> str:
    """添加 Any 导入"""
    lines = content.split('\n')
    
    # 查找 from typing import 行
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            # 检查是否已有 Any
            if 'Any' not in line:
                # 添加 Any
                if line.endswith(')'):
                    # 多行导入
                    lines[i] = line.replace(')', ', Any)')
                else:
                    # 单行导入
                    lines[i] = line.rstrip() + ', Any'
            return '\n'.join(lines)
    
    # 如果没有 from typing import，在第一个 import 后添加
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            lines.insert(i + 1, 'from typing import Any')
            return '\n'.join(lines)
    
    # 如果没有任何 import，在文件开头添加
    lines.insert(0, 'from typing import Any')
    return '\n'.join(lines)


def fix_file(file_path: Path) -> bool:
    """修复单个文件，返回是否有修改"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 应用各种修复
        content = fix_implicit_optional(content)
        content = fix_any_lowercase(content)
        content = fix_object_type_inference(content)
        content = fix_tuple_type_params(content)
        content = fix_missing_return_types(content)
        
        # 如果需要，添加 Any 导入
        if ensure_any_import(content):
            content = add_any_import(content)
        
        # 如果有修改，写回文件
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            logger.info(f"已修复: {file_path}")
            return True
        
        return False
    
    except Exception as e:
        logger.error(f"修复文件失败 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    scraper_path = backend_path / 'apps' / 'automation' / 'services' / 'scraper'
    
    if not scraper_path.exists():
        logger.error(f"scraper 目录不存在: {scraper_path}")
        return
    
    fixed_count = 0
    total_count = 0
    
    # 遍历所有 Python 文件
    for py_file in scraper_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        total_count += 1
        if fix_file(py_file):
            fixed_count += 1
    
    logger.info(f"\n修复完成: {fixed_count}/{total_count} 个文件")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
