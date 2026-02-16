#!/usr/bin/env python3
"""
修复 QuerySet 泛型类型参数

将 QuerySet 修复为 QuerySet[Model]

Requirements: 3.5
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_model_from_file(content: str) -> str | None:
    """从文件中提取主要的 Model 类名"""
    # 查找 from apps.cases.models import XXX
    match = re.search(r'from apps\.cases\.models import (\w+)', content)
    if match:
        return match.group(1)
    
    # 查找 from ..models import XXX
    match = re.search(r'from \.\.models import (\w+)', content)
    if match:
        return match.group(1)
    
    return None


def fix_queryset_types(content: str, model_name: str | None) -> tuple[str, int]:
    """修复 QuerySet 类型参数"""
    if not model_name:
        return content, 0
    
    fixes = 0
    
    # 1. 修复返回类型 -> QuerySet:
    pattern = r'->\s*QuerySet\s*:'
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, f'-> QuerySet[{model_name}]:', content)
    
    # 2. 修复变量注解 : QuerySet
    pattern = r':\s*QuerySet\s*(?=\n|=|\|)'
    matches = list(re.finditer(pattern, content))
    fixes += len(matches)
    content = re.sub(pattern, f': QuerySet[{model_name}]', content)
    
    return content, fixes


def process_file(file_path: Path) -> dict[str, Any]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # 提取 Model 名称
        model_name = extract_model_from_file(content)
        
        if not model_name:
            return {
                'file': str(file_path),
                'fixes': 0,
                'success': True,
                'skipped': True
            }
        
        # 修复 QuerySet 类型
        content, fixes = fix_queryset_types(content, model_name)
        
        # 只有内容变化时才写入
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            return {
                'file': str(file_path),
                'fixes': fixes,
                'model': model_name,
                'success': True
            }
        
        return {
            'file': str(file_path),
            'fixes': 0,
            'success': True
        }
        
    except Exception as e:
        return {
            'file': str(file_path),
            'fixes': 0,
            'success': False,
            'error': str(e)
        }


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / 'apps' / 'cases'
    
    logger.info("开始修复 cases 模块 QuerySet 泛型类型...")
    logger.info(f"扫描目录: {cases_path}\n")
    
    # 收集所有 Python 文件
    py_files = [f for f in cases_path.rglob('*.py') if f.name != '__init__.py']
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")
    
    # 处理文件
    results: list[dict[str, Any]] = []
    modified_files: list[Path] = []
    total_fixes = 0
    
    for py_file in py_files:
        result = process_file(py_file)
        results.append(result)
        
        if result['success'] and result['fixes'] > 0:
            modified_files.append(py_file)
            total_fixes += result['fixes']
            rel_path = py_file.relative_to(backend_path)
            model = result.get('model', '?')
            logger.info(f"  ✓ {rel_path}: {result['fixes']} 处修复 (Model: {model})")
    
    # 输出统计
    logger.info(f"\n修复完成:")
    logger.info(f"  - 修改文件数: {len(modified_files)}")
    logger.info(f"  - 总修复数: {total_fixes}")
    
    # 输出失败的文件
    failed = [r for r in results if not r['success']]
    if failed:
        logger.info(f"\n失败文件 ({len(failed)}):")
        for r in failed:
            logger.info(f"  ✗ {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    main()
