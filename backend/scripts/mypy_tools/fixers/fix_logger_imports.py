#!/usr/bin/env python3
"""批量修复logger导入缺失的错误

修复内容：
1. 扫描所有使用logger的文件
2. 检查是否导入logging
3. 添加 import logging
4. 添加 logger = logging.getLogger(__name__)

Requirements: 2.1
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class LoggerUsageAnalyzer(ast.NodeVisitor):
    """分析logger使用情况的 AST 访问器"""
    
    def __init__(self) -> None:
        self.uses_logger = False
        self.has_logging_import = False
        self.has_logger_init = False
    
    def visit_Import(self, node: ast.Import) -> None:
        """检查 import logging"""
        for alias in node.names:
            if alias.name == 'logging':
                self.has_logging_import = True
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """检查 from logging import ..."""
        if node.module == 'logging':
            self.has_logging_import = True
        self.generic_visit(node)
    
    def visit_Assign(self, node: ast.Assign) -> None:
        """检查 logger = logging.getLogger(__name__)"""
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'logger':
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Attribute):
                        if (isinstance(node.value.func.value, ast.Name) and 
                            node.value.func.value.id == 'logging' and
                            node.value.func.attr == 'getLogger'):
                            self.has_logger_init = True
        self.generic_visit(node)
    
    def visit_Name(self, node: ast.Name) -> None:
        """检查是否使用了logger变量"""
        if node.id == 'logger':
            self.uses_logger = True
        self.generic_visit(node)
    
    def visit_Attribute(self, node: ast.Attribute) -> None:
        """检查logger.info()等调用"""
        if isinstance(node.value, ast.Name) and node.value.id == 'logger':
            self.uses_logger = True
        self.generic_visit(node)


def analyze_logger_usage(content: str) -> dict[str, bool]:
    """分析文件中logger的使用情况
    
    Returns:
        包含uses_logger, has_logging_import, has_logger_init的字典
    """
    try:
        tree = ast.parse(content)
        analyzer = LoggerUsageAnalyzer()
        analyzer.visit(tree)
        
        return {
            'uses_logger': analyzer.uses_logger,
            'has_logging_import': analyzer.has_logging_import,
            'has_logger_init': analyzer.has_logger_init,
        }
    except SyntaxError:
        return {
            'uses_logger': False,
            'has_logging_import': False,
            'has_logger_init': False,
        }


def fix_logger_imports(content: str) -> tuple[str, dict[str, int]]:
    """修复logger导入
    
    Returns:
        (修复后的内容, 修复统计)
    """
    stats = {
        'logging_import': 0,
        'logger_init': 0,
    }
    
    analysis = analyze_logger_usage(content)
    
    # 如果不使用logger，不需要修复
    if not analysis['uses_logger']:
        return content, stats
    
    lines = content.split('\n')
    
    # 查找插入位置
    insert_idx = 0
    last_import_idx = -1
    has_future_import = False
    in_docstring = False
    docstring_quote = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 处理模块级docstring
        if i == 0 or (i == 1 and lines[0].strip().startswith('#')):
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_quote = '"""' if stripped.startswith('"""') else "'''"
                # 检查是否是单行docstring
                if stripped.count(docstring_quote) >= 2:
                    insert_idx = i + 1
                    continue
                else:
                    in_docstring = True
                    continue
        
        # 检查docstring结束
        if in_docstring and docstring_quote and docstring_quote in stripped:
            in_docstring = False
            insert_idx = i + 1
            continue
        
        # 跳过docstring内容
        if in_docstring:
            continue
        
        # 记录 from __future__ import
        if stripped.startswith('from __future__'):
            has_future_import = True
            insert_idx = i + 1
        
        # 记录最后一个import语句的位置
        if stripped.startswith('import ') or stripped.startswith('from '):
            last_import_idx = i
    
    # 确定插入位置
    if last_import_idx >= 0:
        insert_idx = last_import_idx + 1
    
    # 跳过空行
    while insert_idx < len(lines) and not lines[insert_idx].strip():
        insert_idx += 1
    
    # 添加 import logging
    if not analysis['has_logging_import']:
        lines.insert(insert_idx, 'import logging')
        stats['logging_import'] = 1
        insert_idx += 1
        
        # 添加空行分隔
        if insert_idx < len(lines) and lines[insert_idx].strip():
            lines.insert(insert_idx, '')
            insert_idx += 1
    
    # 添加 logger = logging.getLogger(__name__)
    if not analysis['has_logger_init']:
        # 查找合适的位置（在所有import之后）
        logger_insert_idx = insert_idx
        
        # 跳过剩余的import语句
        for i in range(insert_idx, len(lines)):
            stripped = lines[i].strip()
            if stripped and not (stripped.startswith('import ') or stripped.startswith('from ') or stripped.startswith('#')):
                logger_insert_idx = i
                break
        
        # 确保在logger初始化前有空行
        if logger_insert_idx > 0 and lines[logger_insert_idx - 1].strip():
            lines.insert(logger_insert_idx, '')
            logger_insert_idx += 1
        
        lines.insert(logger_insert_idx, 'logger = logging.getLogger(__name__)')
        stats['logger_init'] = 1
        
        # 确保在logger初始化后有空行
        if logger_insert_idx + 1 < len(lines) and lines[logger_insert_idx + 1].strip():
            lines.insert(logger_insert_idx + 1, '')
    
    return '\n'.join(lines), stats


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件
    
    Returns:
        修复结果字典
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复logger导入
        content, stats = fix_logger_imports(content)
        
        # 只有在有修改时才写入
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return {'success': True, 'modified': True, 'stats': stats}
        
        return {'success': True, 'modified': False, 'stats': stats}
        
    except Exception as e:
        logger.error(f"错误处理文件 {file_path}: {e}")
        return {'success': False, 'modified': False, 'error': str(e)}


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / 'apps'
    
    if not apps_path.exists():
        logger.error(f"apps 目录不存在: {apps_path}")
        return
    
    logger.info("开始批量修复logger导入缺失错误...")
    logger.info(f"扫描目录: {apps_path}\n")
    
    total_stats = {
        'files': 0,
        'logging_import': 0,
        'logger_init': 0,
    }
    
    # 遍历所有 Python 文件
    py_files = list(apps_path.rglob('*.py'))
    logger.info(f"找到 {len(py_files)} 个 Python 文件\n")
    
    for py_file in py_files:
        # 跳过 __init__.py 和 migrations
        if py_file.name == '__init__.py' or 'migrations' in py_file.parts:
            continue
        
        result = fix_file(py_file)
        if result['success'] and result['modified']:
            stats = result['stats']
            total_stats['files'] += 1
            total_stats['logging_import'] += stats['logging_import']
            total_stats['logger_init'] += stats['logger_init']
            
            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            if any(stats.values()):
                fixes = []
                if stats['logging_import'] > 0:
                    fixes.append("添加 import logging")
                if stats['logger_init'] > 0:
                    fixes.append("添加 logger 初始化")
                logger.info(f"  {', '.join(fixes)}")
    
    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  添加 import logging: {total_stats['logging_import']}")
    logger.info(f"  添加 logger 初始化: {total_stats['logger_init']}")
    total_fixes = total_stats['logging_import'] + total_stats['logger_init']
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == '__main__':
    main()
