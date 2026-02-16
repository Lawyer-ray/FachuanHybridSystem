"""UntypedDefFixer - 修复no-untyped-def错误"""

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


class UntypedDefFixer(BatchFixer):
    """修复no-untyped-def错误"""

    # 需要手动修复的复杂模式
    MANUAL_FIX_PATTERNS = [
        "*args",  # 可变参数需要仔细分析
        "**kwargs",  # 关键字参数需要仔细分析
        "Callable",  # 回调函数类型复杂
        "Generic",  # 泛型函数需要TypeVar
        "overload",  # 重载函数需要特殊处理
    ]

    def __init__(self, backend_path: Path | None = None) -> None:
        """初始化UntypedDefFixer"""
        super().__init__(fix_pattern="no-untyped-def", backend_path=backend_path)

    def can_fix(self, error: ErrorRecord) -> bool:
        """
        判断是否可以修复此错误

        Args:
            error: 错误记录

        Returns:
            是否可以修复
        """
        if error.error_code != "no-untyped-def":
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
                error_message=f"文件不存在: {file_path}",
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
                error_message="AST解析失败",
            )

        # 收集需要添加类型注解的函数
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
                error_message=None,
            )

        # 修改AST，添加类型注解
        transformer = FunctionTypeAnnotationAdder(functions_to_fix)
        modified_tree = transformer.visit(tree)

        if transformer.modified:
            # 写回文件
            if self.write_source(full_path, modified_tree):
                errors_fixed = transformer.functions_fixed
                logger.info(f"成功修复文件 {file_path}，" f"为 {errors_fixed} 个函数添加了类型注解")
            else:
                return FixResult(
                    file_path=file_path,
                    errors_fixed=0,
                    errors_remaining=len(errors),
                    fix_pattern=self.fix_pattern,
                    success=False,
                    error_message="写入文件失败",
                )

        return FixResult(
            file_path=file_path,
            errors_fixed=transformer.functions_fixed,
            errors_remaining=len(errors) - transformer.functions_fixed,
            fix_pattern=self.fix_pattern,
            success=True,
            error_message=None,
        )


class FunctionTypeAnnotationAdder(ast.NodeTransformer):
    """为函数添加类型注解的AST转换器"""

    def __init__(self, functions_to_fix: dict[int, ErrorRecord]) -> None:
        """
        初始化转换器

        Args:
            functions_to_fix: {行号: 错误记录}
        """
        self.functions_to_fix = functions_to_fix
        self.modified = False
        self.functions_fixed = 0
        self.current_line = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """访问函数定义节点"""
        # 检查是否是需要修复的函数
        if node.lineno not in self.functions_to_fix:
            return node

        logger.info(f"处理函数: {node.name} (行 {node.lineno})")

        # 检查是否需要添加参数类型注解
        needs_param_annotations = self._needs_parameter_annotations(node)

        # 检查是否需要添加返回值类型注解
        needs_return_annotation = node.returns is None

        if needs_param_annotations:
            self._add_parameter_annotations(node)

        if needs_return_annotation:
            self._add_return_annotation(node)

        if needs_param_annotations or needs_return_annotation:
            self.modified = True
            self.functions_fixed += 1
            logger.info(f"为函数 {node.name} 添加了类型注解")

        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        """访问异步函数定义节点"""
        # 检查是否是需要修复的函数
        if node.lineno not in self.functions_to_fix:
            return node

        logger.info(f"处理异步函数: {node.name} (行 {node.lineno})")

        # 检查是否需要添加参数类型注解
        needs_param_annotations = self._needs_parameter_annotations(node)

        # 检查是否需要添加返回值类型注解
        needs_return_annotation = node.returns is None

        if needs_param_annotations:
            self._add_parameter_annotations(node)

        if needs_return_annotation:
            self._add_return_annotation(node)

        if needs_param_annotations or needs_return_annotation:
            self.modified = True
            self.functions_fixed += 1
            logger.info(f"为异步函数 {node.name} 添加了类型注解")

        return node

    def _needs_parameter_annotations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """检查函数是否需要添加参数类型注解"""
        # 检查所有参数（不包括self和cls）
        for arg in node.args.args:
            # 跳过self和cls
            if arg.arg in ("self", "cls"):
                continue

            # 如果参数没有类型注解，需要添加
            if arg.annotation is None:
                return True

        return False

    def _add_parameter_annotations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """为函数参数添加类型注解"""
        for arg in node.args.args:
            # 跳过self和cls
            if arg.arg in ("self", "cls"):
                continue

            # 如果参数没有类型注解，添加Any
            if arg.annotation is None:
                arg.annotation = self._infer_parameter_type(node, arg.arg)
                logger.debug(f"为参数 {arg.arg} 添加类型注解")

    def _add_return_annotation(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """为函数添加返回值类型注解"""
        # 推断返回值类型
        return_type = self._infer_return_type(node)
        node.returns = return_type
        logger.debug(f"为函数 {node.name} 添加返回值类型注解")

    def _infer_parameter_type(self, func: ast.FunctionDef | ast.AsyncFunctionDef, param_name: str) -> ast.expr:
        """
        推断参数类型

        Args:
            func: 函数节点
            param_name: 参数名

        Returns:
            类型注解AST节点
        """
        # 简单策略：分析参数在函数体中的使用
        # 1. 检查是否有类型检查（isinstance）
        # 2. 检查是否调用了特定方法
        # 3. 默认使用Any

        for node in ast.walk(func):
            # 检查isinstance调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "isinstance" and len(node.args) >= 2:

                    # 检查第一个参数是否是我们要推断的参数
                    if isinstance(node.args[0], ast.Name) and node.args[0].id == param_name:

                        # 第二个参数是类型
                        type_arg = node.args[1]
                        if isinstance(type_arg, ast.Name):
                            return ast.Name(id=type_arg.id, ctx=ast.Load())

        # 默认返回Any
        return ast.Name(id="Any", ctx=ast.Load())

    def _infer_return_type(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.expr:
        """
        推断返回值类型

        Args:
            func: 函数节点

        Returns:
            类型注解AST节点
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
        if all(v is None or (isinstance(v, ast.Constant) and v.value is None) for v in return_values):
            return ast.Constant(value=None)

        # 分析return值的类型
        inferred_types: set[str] = set()

        for ret_val in return_values:
            if ret_val is None:
                inferred_types.add("None")
            elif isinstance(ret_val, ast.Constant):
                # 常量类型
                if isinstance(ret_val.value, bool):
                    inferred_types.add("bool")
                elif isinstance(ret_val.value, int):
                    inferred_types.add("int")
                elif isinstance(ret_val.value, str):
                    inferred_types.add("str")
                elif isinstance(ret_val.value, float):
                    inferred_types.add("float")
                elif ret_val.value is None:
                    inferred_types.add("None")
            elif isinstance(ret_val, ast.List):
                inferred_types.add("list")
            elif isinstance(ret_val, ast.Dict):
                inferred_types.add("dict")
            elif isinstance(ret_val, ast.Set):
                inferred_types.add("set")
            elif isinstance(ret_val, ast.Tuple):
                inferred_types.add("tuple")

        # 如果只有一种类型，返回该类型
        if len(inferred_types) == 1:
            type_name = inferred_types.pop()
            if type_name == "None":
                return ast.Constant(value=None)
            return ast.Name(id=type_name, ctx=ast.Load())

        # 如果有多种类型，返回Any（简化处理）
        return ast.Name(id="Any", ctx=ast.Load())
