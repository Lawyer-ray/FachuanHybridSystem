"""批量修复常见的mypy错误"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_missing_typing_imports(backend_path: Path) -> int:
    """修复缺少的typing导入"""
    logger.info("修复缺少的typing导入...")
    
    # 常见的typing类型
    typing_types = {
        'Dict', 'List', 'Set', 'Tuple', 'Optional', 'Union', 
        'Callable', 'Type', 'TypeVar', 'Generic', 'Protocol',
        'Literal', 'Final', 'ClassVar', 'Sequence', 'Iterable'
    }
    
    fixed = 0
    
    # 查找所有Python文件
    for py_file in backend_path.glob('apps/**/*.py'):
        content = py_file.read_text(encoding='utf-8')
        
        # 检查是否使用了typing类型但没有导入
        needs_import = set()
        for type_name in typing_types:
            if f'{type_name}[' in content or f': {type_name}' in content:
                # 检查是否已导入
                if f'from typing import' in content:
                    if type_name not in content.split('from typing import')[1].split('\n')[0]:
                        needs_import.add(type_name)
                else:
                    needs_import.add(type_name)
        
        if needs_import:
            lines = content.split('\n')
            
            # 查找typing导入行
            typing_line_idx = -1
            for i, line in enumerate(lines):
                if line.strip().startswith('from typing import'):
                    typing_line_idx = i
                    break
            
            if typing_line_idx >= 0:
                # 添加到现有导入
                import_line = lines[typing_line_idx]
                for type_name in sorted(needs_import):
                    if type_name not in import_line:
                        import_line = import_line.rstrip() + f', {type_name}'
                lines[typing_line_idx] = import_line
                
                py_file.write_text('\n'.join(lines), encoding='utf-8')
                fixed += len(needs_import)
                logger.info(f"修复 {py_file.relative_to(backend_path)} - 添加 {', '.join(needs_import)}")
    
    return fixed


def fix_django_model_id_fields(backend_path: Path) -> int:
    """为Django Model添加常见的_id字段注解"""
    logger.info("修复Django Model _id字段...")
    
    fixed = 0
    
    # 查找所有models.py文件
    for model_file in backend_path.glob('apps/**/models.py'):
        content = model_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        modified = False
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 查找Model类定义
            if re.match(r'\s*class\s+\w+\s*\(.*Model.*\):', line):
                class_match = re.match(r'(\s*)class\s+(\w+)', line)
                if class_match:
                    indent = class_match.group(1)
                    class_name = class_match.group(2)
                    
                    # 跳过docstring
                    j = i + 1
                    while j < len(lines) and (lines[j].strip().startswith('"""') or 
                                              lines[j].strip().startswith("'''") or
                                              '"""' in lines[j] or "'''" in lines[j] or
                                              lines[j].strip() == ''):
                        j += 1
                    
                    # 检查是否已有id注解
                    if j < len(lines) and 'id:' not in '\n'.join(lines[i:j+10]):
                        # 添加id注解
                        lines.insert(j, f"{indent}    id: int  # Django自动生成的主键")
                        modified = True
                        fixed += 1
                        logger.info(f"添加 {model_file.relative_to(backend_path)} - {class_name}.id")
            
            i += 1
        
        if modified:
            model_file.write_text('\n'.join(lines), encoding='utf-8')
    
    return fixed


def fix_type_ignore_comments(backend_path: Path) -> int:
    """为无法自动修复的错误添加type: ignore注释"""
    logger.info("为复杂错误添加type: ignore...")
    
    # 这个功能暂时跳过，因为会降低类型安全性
    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("=" * 60)
    logger.info("开始批量修复常见错误")
    logger.info("=" * 60)
    
    # 统计初始错误数
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    initial_errors = len([line for line in result.stdout.split('\n') if ': error:' in line])
    logger.info(f"初始错误数: {initial_errors}")
    
    # 执行修复
    total_fixed = 0
    
    # 1. 修复typing导入
    fixed = fix_missing_typing_imports(backend_path)
    total_fixed += fixed
    logger.info(f"修复typing导入: {fixed}个")
    
    # 2. 修复Django Model id字段
    fixed = fix_django_model_id_fields(backend_path)
    total_fixed += fixed
    logger.info(f"修复Model id字段: {fixed}个")
    
    # 统计最终错误数
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    final_errors = len([line for line in result.stdout.split('\n') if ': error:' in line])
    
    logger.info("=" * 60)
    logger.info(f"修复完成")
    logger.info(f"初始错误: {initial_errors}")
    logger.info(f"最终错误: {final_errors}")
    logger.info(f"修复数量: {initial_errors - final_errors}")
    logger.info(f"操作数量: {total_fixed}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
