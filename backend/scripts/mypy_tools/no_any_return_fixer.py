"""NoAnyReturnFixer - 修复no-any-return错误"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .batch_fixer import BatchFixer

if TYPE_CHECKING:
    from .error_analyzer import ErrorRecord
    from .validation_system import FixResult

logger = logging.getLogger(__name__)


class NoAnyReturnFixer(BatchFixer):
    """修复no-any-return错误"""
    
    # 需要手动修复的复杂模式
    MANUAL_FIX_PATTERNS = [
        'Protocol',  # Protocol类型需要仔细设计
        'Callable',  # 回调函数返回类型复杂
        'Generic',  # 泛型返回类型需要TypeVar
        'overload',  # 重载函数需要特殊处理
    ]
    
    def __init__(self, backend_path: Path | None = None) -> None:
        """初始化NoAnyReturnFixer"""
        super().__init__(fix_pattern='no-any-return', backend_path=backend_path)
    
    def can_fix(self, error: ErrorRecord) -> bool:
        """
        判断是否可以修复此错误
        
        Args:
            error: 错误记录
            
        Returns:
            是否可以修复
        """
        if error.error_code != 'no-any-return':
            return False
        
        # 检查是否是需要手动修复的复杂情况
        for pattern in self.MANUAL_FIX_PATTERNS:
            if pattern in error.message:
                logger.debug(f"需要手动修复: {error.message}")
                return False
        
        # 简单函数可以自动修复
        return True
    
    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """
        修复文件中的错误
        
        Args:
            file_path: 文件路径
            errors: 该文件中的错误列表
            
        Returns:
            修复结果
        """
        from .validation_system import FixResult
        
        full_path = self.backend_path / file_path
        
        if not full_path.exists():
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message=f"文件不存在: {file_path}"
            )
        
        # 解析AST
        tree = self.parse_ast(full_path)
        if tree is None:
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message="AST解析失败"
            )
        
        # 收集需要修复返回类型的函数
        functions_to_fix: dict[int, ErrorRecord] = {}
        
        for error in errors:
            if not self.can_fix(error):
                continue
            
            # 使用行号作为键
            functions_to_fix[error.line] = error
        
        if not functions_to_fix:
            logger.info(f"文件 {file_path} 中没有可自动修复的错误")
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=True,
                error_message=None
            )
        
        # 修改AST，替换Any返回类型
        transformer = ReturnTypeReplacer(functions_to_fix)
        modified_tree = transformer.visit(tree)
        
        if transformer.modified:
            # 写回文件
            if self.write_source(full_path, modified_tree):
                errors_fixed = transformer.functions_fixed
                logger.info(
                    f"成功修复文件 {file_path}，"
                    f"为 {errors_fixed} 个函数替换了返回类型"
                )
            else:
                return FixResult(
                    file_path=file_path,
                    errors_fixed=0,
                    errors_remaining=len(errors),
                    fix_pattern=self.fix_pattern,
                    success=False,
                    error_message="写入文件失败"
                )
        
        return FixResult(
            file_path=file_path,
            errors_fixed=transformer.functions_fixed,
            errors_remaining=len(errors) - transformer.functions_fixed,
            fix_pattern=self.fix_pattern,
            success=True,
            error_message=None
        )


class ReturnTypeReplacer(ast.NodeTransformer):
    """替换函数返回类型的AST转换器"""
    
    def __init__(self, functions_to_fix: dict[int, ErrorRecord]) -> None:
        """
        初始化转换器
        
        Args:
            functions_to_fix: {行号: 错误记录}
        """
        self.functions_to_fix = functions_to_fix
        self.modified = False
        self.functions_fixed = 0
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """访问函数定义节点"""
        # 检查是否是需要修复的函数
        if node.lineno not in self.functions_to_fix:
            return node
        
        logger.info(f"处理函数: {node.name} (行 {node.lineno})")
        
        # 推断返回值类型
        inferred_type = self._infer_return_type(node)
        
        # 如果推断出的类型不是Any，则替换
        if inferred_type is not None and not self._is_any_type(inferred_type):
            node.returns = inferred_type
            self.modified = True
            self.functions_fixed += 1
            logger.info(f"为函数 {node.name} 替换了返回类型")
        else:
            logger.debug(f"函数 {node.name} 无法推断具体类型，保持Any")
        
        return node
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        """访问异步函数定义节点"""
        # 检查是否是需要修复的函数
        if node.lineno not in self.functions_to_fix:
            return node
        
        logger.info(f"处理异步函数: {node.name} (行 {node.lineno})")
        
        # 推断返回值类型
        inferred_type = self._infer_return_type(node)
        
        # 如果推断出的类型不是Any，则替换
        if inferred_type is not None and not self._is_any_type(inferred_type):
            node.returns = inferred_type
            self.modified = True
            self.functions_fixed += 1
            logger.info(f"为异步函数 {node.name} 替换了返回类型")
        else:
            logger.debug(f"异步函数 {node.name} 无法推断具体类型，保持Any")
        
        return node
    
    def _is_any_type(self, node: ast.expr) -> bool:
        """检查类型注解是否是Any"""
        if isinstance(node, ast.Name) and node.id == 'Any':
            return True
        return False
    
    def _infer_return_type(
        self, 
        func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.expr | None:
        """
        推断返回值类型
        
        Args:
            func: 函数节点
            
        Returns:
            类型注解AST节点，无法推断返回None
        """
        # 收集所有return语句
        return_values: list[ast.expr | None] = []
        
        for node in ast.walk(func):
            if isinstance(node, ast.Return):
                return_values.append(node.value)
        
        # 如果没有return语句，返回None
        if not return_values:
            return ast.Constant(value=None)
        
        # 如果所有return都是None，返回None
        if all(v is None or (isinstance(v, ast.Constant) and v.value is None) 
               for v in return_values):
            return ast.Constant(value=None)
        
        # 分析return值的类型
        inferred_types: list[str] = []
        
        for ret_val in return_values:
            if ret_val is None:
                inferred_types.append('None')
            else:
                type_name = self._infer_expression_type(ret_val)
                if type_name:
                    inferred_types.append(type_name)
        
        # 去重
        unique_types = list(dict.fromkeys(inferred_types))
        
        # 如果只有一种类型，返回该类型
        if len(unique_types) == 1:
            type_name = unique_types[0]
            return self._create_type_node(type_name)
        
        # 如果有多种类型，使用Union
        if len(unique_types) > 1:
            return self._create_union_type(unique_types)
        
        # 无法推断，返回None（保持Any）
        return None
    
    def _infer_expression_type(self, expr: ast.expr) -> str | None:
        """
        推断表达式的类型
        
        Args:
            expr: 表达式节点
            
        Returns:
            类型名称字符串，无法推断返回None
        """
        # 常量类型
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return 'bool'
            elif isinstance(expr.value, int):
                return 'int'
            elif isinstance(expr.value, str):
                return 'str'
            elif isinstance(expr.value, float):
                return 'float'
            elif expr.value is None:
                return 'None'
        
        # 容器类型
        elif isinstance(expr, ast.List):
            # 分析列表元素类型
            if expr.elts:
                elem_types = set()
                for elt in expr.elts[:5]:  # 只分析前5个元素
                    elem_type = self._infer_expression_type(elt)
                    if elem_type:
                        elem_types.add(elem_type)
                
                if len(elem_types) == 1:
                    elem_type = elem_types.pop()
                    return f'list[{elem_type}]'
            return 'list[Any]'
        
        elif isinstance(expr, ast.Dict):
            # 分析字典键值类型
            if expr.keys and expr.values:
                key_types = set()
                val_types = set()
                
                for key, val in zip(expr.keys[:5], expr.values[:5]):  # 只分析前5对
                    if key:
                        key_type = self._infer_expression_type(key)
                        if key_type:
                            key_types.add(key_type)
                    
                    val_type = self._infer_expression_type(val)
                    if val_type:
                        val_types.add(val_type)
                
                if len(key_types) == 1 and len(val_types) == 1:
                    key_type = key_types.pop()
                    val_type = val_types.pop()
                    return f'dict[{key_type}, {val_type}]'
            return 'dict[str, Any]'
        
        elif isinstance(expr, ast.Set):
            # 分析集合元素类型
            if expr.elts:
                elem_types = set()
                for elt in expr.elts[:5]:
                    elem_type = self._infer_expression_type(elt)
                    if elem_type:
                        elem_types.add(elem_type)
                
                if len(elem_types) == 1:
                    elem_type = elem_types.pop()
                    return f'set[{elem_type}]'
            return 'set[Any]'
        
        elif isinstance(expr, ast.Tuple):
            # 元组类型
            if expr.elts:
                elem_types = []
                for elt in expr.elts:
                    elem_type = self._infer_expression_type(elt)
                    if elem_type:
                        elem_types.append(elem_type)
                    else:
                        elem_types.append('Any')
                
                if len(elem_types) <= 5:  # 只处理小元组
                    return f"tuple[{', '.join(elem_types)}]"
            return 'tuple[Any, ...]'
        
        # 函数调用 - 尝试从函数名推断
        elif isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                func_name = expr.func.id
                
                # 常见构造函数
                if func_name in ('list', 'List'):
                    return 'list[Any]'
                elif func_name in ('dict', 'Dict'):
                    return 'dict[str, Any]'
                elif func_name in ('set', 'Set'):
                    return 'set[Any]'
                elif func_name in ('tuple', 'Tuple'):
                    return 'tuple[Any, ...]'
                elif func_name in ('str', 'int', 'float', 'bool'):
                    return func_name
        
        # 属性访问 - 可能是QuerySet等
        elif isinstance(expr, ast.Attribute):
            # 检查是否是QuerySet方法
            if expr.attr in ('all', 'filter', 'exclude', 'order_by'):
                return 'QuerySet[Any]'
            elif expr.attr in ('first', 'last', 'get'):
                return 'Any | None'
        
        # 无法推断
        return None
    
    def _create_type_node(self, type_str: str) -> ast.expr:
        """
        创建类型注解AST节点
        
        Args:
            type_str: 类型字符串，如 'int', 'list[str]'
            
        Returns:
            类型注解AST节点
        """
        # 简单类型
        if type_str in ('int', 'str', 'bool', 'float', 'None'):
            if type_str == 'None':
                return ast.Constant(value=None)
            return ast.Name(id=type_str, ctx=ast.Load())
        
        # 处理泛型类型，如 list[str]
        if '[' in type_str:
            base_type, params_str = type_str.split('[', 1)
            params_str = params_str.rstrip(']')
            
            # 分割参数
            params = [p.strip() for p in params_str.split(',')]
            
            base_node = ast.Name(id=base_type, ctx=ast.Load())
            
            if len(params) == 1:
                # 单参数泛型
                param_node = self._create_type_node(params[0])
                return ast.Subscript(
                    value=base_node,
                    slice=param_node,
                    ctx=ast.Load()
                )
            else:
                # 多参数泛型
                param_nodes = [self._create_type_node(p) for p in params]
                return ast.Subscript(
                    value=base_node,
                    slice=ast.Tuple(elts=param_nodes, ctx=ast.Load()),
                    ctx=ast.Load()
                )
        
        # 处理Union类型，如 str | int
        if '|' in type_str:
            types = [t.strip() for t in type_str.split('|')]
            return self._create_union_type(types)
        
        # 其他情况，作为简单名称
        return ast.Name(id=type_str, ctx=ast.Load())
    
    def _create_union_type(self, types: list[str]) -> ast.expr:
        """
        创建Union类型注解
        
        Args:
            types: 类型名称列表
            
        Returns:
            Union类型注解AST节点
        """
        if not types:
            return ast.Name(id='Any', ctx=ast.Load())
        
        if len(types) == 1:
            return self._create_type_node(types[0])
        
        # 使用 | 操作符创建Union（Python 3.10+）
        # 例如: str | int | None
        type_nodes = [self._create_type_node(t) for t in types]
        
        # 构建BinOp链: a | b | c
        result = type_nodes[0]
        for type_node in type_nodes[1:]:
            result = ast.BinOp(
                left=result,
                op=ast.BitOr(),
                right=type_node
            )
        
        return result
