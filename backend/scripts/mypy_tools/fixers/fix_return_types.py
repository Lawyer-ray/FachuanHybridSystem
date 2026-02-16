#!/usr/bin/env python3
"""批量修复函数返回类型注解缺失的错误

修复内容：
1. 使用AST解析识别函数
2. 检查返回类型注解
3. 为无返回值函数添加 -> None
4. 为有返回值函数添加具体类型（基于返回语句推断）

Requirements: 2.1, 2.3
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ReturnTypeAnalyzer(ast.NodeVisitor):
    """分析函数返回类型的 AST 访问器"""
    
    def __init__(self) -> None:
        self.functions_to_fix: list[dict[str, Any]] = []
        self.current_class: str | None = None
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """访问类定义"""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """访问函数定义"""
        self._check_function(node)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """访问异步函数定义"""
        self._check_function(node)
        self.generic_visit(node)
    
    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """检查函数是否需要添加返回类型"""
        # 跳过已有返回类型注解的函数
        if node.returns is not None:
            return
        
        # 跳过特殊方法（除了 __init__）
        if node.name.startswith('__') and node.name.endswith('__') and node.name != '__init__':
            return
        
        # 分析返回语句
        return_type = self._infer_return_type(node)
        
        if return_type:
            self.functions_to_fix.append({
                'name': node.name,
                'lineno': node.lineno,
                'col_offset': node.col_offset,
                'return_type': return_type,
                'is_async': isinstance(node, ast.AsyncFunctionDef),
                'in_class': self.current_class,
            })
    
    def _infer_return_type(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        """推断函数返回类型"""
        returns: list[ast.Return] = []
        
        # 收集所有 return 语句
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                returns.append(child)
        
        # 没有 return 语句或只有空 return
        if not returns or all(r.value is None for r in returns):
            return 'None'
        
        # 有返回值的情况，尝试推断类型
        return_values = [r.value for r in returns if r.value is not None]
        
        if not return_values:
            return 'None'
        
        # 简单类型推断
        inferred_types = set()
        for value in return_values:
            inferred = self._infer_expr_type(value)
            if inferred:
                inferred_types.add(inferred)
        
        # 如果所有返回值类型一致
        if len(inferred_types) == 1:
            return inferred_types.pop()
        
        # 如果有多种类型，使用 Any
        if len(inferred_types) > 1:
            return 'Any'
        
        # 无法推断，使用 Any
        return 'Any'
    
    def _infer_expr_type(self, node: ast.expr) -> str | None:
        """推断表达式类型"""
        if isinstance(node, ast.Constant):
            value = node.value
            if value is None:
                return 'None'
            elif isinstance(value, bool):
                return 'bool'
            elif isinstance(value, int):
                return 'int'
            elif isinstance(value, float):
                return 'float'
            elif isinstance(value, str):
                return 'str'
            elif isinstance(value, bytes):
                return 'bytes'
        elif isinstance(node, ast.List):
            return 'list[Any]'
        elif isinstance(node, ast.Dict):
            return 'dict[str, Any]'
        elif isinstance(node, ast.Set):
            return 'set[Any]'
        elif isinstance(node, ast.Tuple):
            return 'tuple[Any, ...]'
        elif isinstance(node, ast.Call):
            # 尝试从函数调用推断
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in ('dict', 'Dict'):
                    return 'dict[str, Any]'
                elif func_name in ('list', 'List'):
                    return 'list[Any]'
                elif func_name in ('set', 'Set'):
                    return 'set[Any]'
                elif func_name in ('tuple', 'Tuple'):
                    return 'tuple[Any, ...]'
                elif func_name in ('str',):
                    return 'str'
                elif func_name in ('int',):
                    return 'int'
                elif func_name in ('float',):
                    return 'float'
                elif func_name in ('bool',):
                    return 'bool'
        
        return None


def fix_return_types(content: str, file_path: Path) -> tuple[str, dict[str, int]]:
    """为函数添加返回类型注解
    
    Returns:
        (修复后的内容, 修复统计)
    """
    stats = {
        'none': 0,
        'typed': 0,
    }
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.warning(f"语法错误，跳过: {file_path}")
        return content, stats
    
    analyzer = ReturnTypeAnalyzer()
    analyzer.visit(tree)
    
    if not analyzer.functions_to_fix:
        return content, stats
    
    # 按行号倒序排序，从后往前修改，避免行号偏移
    functions = sorted(analyzer.functions_to_fix, key=lambda x: x['lineno'], reverse=True)
    
    lines = content.split('\n')
    
    for func in functions:
        lineno = func['lineno'] - 1  # AST 行号从 1 开始
        return_type = func['return_type']
        
        # 查找函数定义的结束位置（找到右括号后的冒号）
        current_line = lineno
        paren_depth = 0
        found_opening_paren = False
        in_string = False
        string_char = None
        
        while current_line < len(lines):
            line = lines[current_line]
            
            # 跟踪括号深度和字符串状态
            i = 0
            while i < len(line):
                char = line[i]
                
                # 处理字符串
                if char in ('"', "'"):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and (i == 0 or line[i-1] != '\\'):
                        in_string = False
                        string_char = None
                
                # 只在非字符串中计数括号
                if not in_string:
                    if char == '(':
                        paren_depth += 1
                        found_opening_paren = True
                    elif char == ')':
                        paren_depth -= 1
                        # 当括号闭合时，查找后面的冒号
                        if paren_depth == 0 and found_opening_paren:
                            # 查找这个右括号后的冒号
                            rest_of_line = line[i+1:]
                            # 跳过空格
                            rest_stripped = rest_of_line.lstrip()
                            if rest_stripped.startswith(':'):
                                # 找到冒号的实际位置
                                spaces_before_colon = len(rest_of_line) - len(rest_stripped)
                                colon_pos = i + 1 + spaces_before_colon
                                # 在冒号前插入返回类型
                                lines[current_line] = line[:colon_pos] + f' -> {return_type}' + line[colon_pos:]
                                
                                if return_type == 'None':
                                    stats['none'] += 1
                                else:
                                    stats['typed'] += 1
                                break
                
                i += 1
            
            # 如果已经找到并处理了函数定义，退出
            if paren_depth == 0 and found_opening_paren:
                break
            
            current_line += 1
            if current_line >= len(lines):
                break
    
    modified_content = '\n'.join(lines)
    
    # 检查是否需要添加 Any 导入
    if 'Any' in modified_content and stats['typed'] > 0:
        modified_content = ensure_typing_imports(modified_content, needs_any=True)
    
    return modified_content, stats


def ensure_typing_imports(content: str, needs_any: bool = False) -> str:
    """确保导入了必要的类型"""
    if not needs_any:
        return content
    
    # 检查是否已经导入了 Any
    if 'from typing import' in content and 'Any' in content.split('from typing import')[1].split('\n')[0]:
        return content
    
    lines = content.split('\n')
    
    # 查找 from typing import 行
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('from typing import'):
            typing_import_idx = i
            break
    
    if typing_import_idx >= 0:
        # 在现有导入中添加 Any
        line = lines[typing_import_idx]
        
        # 处理多行导入（括号）
        if '(' in line:
            # 查找右括号
            for j in range(typing_import_idx, len(lines)):
                if ')' in lines[j]:
                    # 检查是否已有 Any
                    import_block = '\n'.join(lines[typing_import_idx:j+1])
                    if 'Any' not in import_block:
                        lines[j] = lines[j].replace(')', ', Any)')
                    break
        else:
            # 单行导入，检查是否已有 Any
            if 'Any' not in line:
                lines[typing_import_idx] = line.rstrip() + ', Any'
    else:
        # 添加新的导入行
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('from __future__'):
                insert_idx = i + 1
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
            elif line.startswith('import ') or line.startswith('from '):
                insert_idx = i
                break
        
        lines.insert(insert_idx, 'from typing import Any')
        if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
            lines.insert(insert_idx + 1, '')
    
    return '\n'.join(lines)


def fix_file(file_path: Path) -> dict[str, Any]:
    """修复单个文件
    
    Returns:
        修复结果字典
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 修复返回类型
        content, stats = fix_return_types(content, file_path)
        
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
    
    logger.info("开始批量修复函数返回类型注解缺失错误...")
    logger.info(f"扫描目录: {apps_path}\n")
    
    total_stats = {
        'files': 0,
        'none': 0,
        'typed': 0,
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
            total_stats['none'] += stats['none']
            total_stats['typed'] += stats['typed']
            
            rel_path = py_file.relative_to(backend_path)
            logger.info(f"✓ {rel_path}")
            if any(stats.values()):
                fixes = []
                if stats['none'] > 0:
                    fixes.append(f"-> None: {stats['none']}")
                if stats['typed'] > 0:
                    fixes.append(f"-> 类型: {stats['typed']}")
                logger.info(f"  {', '.join(fixes)}")
    
    logger.info(f"\n修复完成:")
    logger.info(f"  修复文件数: {total_stats['files']}")
    logger.info(f"  添加 -> None: {total_stats['none']}")
    logger.info(f"  添加具体类型: {total_stats['typed']}")
    total_fixes = total_stats['none'] + total_stats['typed']
    logger.info(f"  总修复数: {total_fixes}")


if __name__ == '__main__':
    main()
