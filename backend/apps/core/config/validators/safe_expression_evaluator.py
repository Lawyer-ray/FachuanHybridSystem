"""Module for safe expression evaluator."""

from __future__ import annotations

"""
安全表达式解析器

替代 eval() 的安全实现,仅支持比较运算和逻辑运算,不执行任意代码.
"""

import ast
import operator
from typing import Any, ClassVar


class SafeExpressionEvaluator:
    """
    安全的表达式求值器,替代 eval(, cast).
    仅支持比较运算和逻辑运算,不执行任意代码.

    支持的操作:
    - 比较运算符: ==, !=, <, <=, >, >=, in, not in
    - 逻辑运算符: and, or, not
    - 字面量: 字符串、数字、布尔值、None、列表、元组
    - 变量引用: 通过 allowed_names 字典提供
    """

    # 支持的比较运算符
    COMPARE_OPS: ClassVar = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }

    def __init__(self, allowed_names: dict[str, Any] | None = None) -> None:
        """
        初始化安全表达式求值器.

        Args:
            allowed_names: 允许在表达式中使用的变量名和值的映射
        """
        self.allowed_names = allowed_names or {}
        # 添加内置常量
        self._builtins = {
            "True": True,
            "False": False,
            "None": None,
        }

    def evaluate(self, expression: str) -> Any:
        """
        安全地评估表达式.

        Args:
            expression: 要评估的表达式字符串

        Returns:
            表达式的评估结果

        Raises:
            ValueError: 当表达式包含不支持的语法时
            SyntaxError: 当表达式语法错误时
        """
        try:
            tree = ast.parse(expression, mode="eval")
            return self._eval_node(tree.body)
        except SyntaxError as e:
            raise SyntaxError(f"表达式语法错误: {e}") from e

    def _eval_node(self, node: ast.AST) -> Any:
        """
        递归评估 AST 节点.
        """
        _DISPATCH = {
            ast.Constant: lambda n: n.value,
            ast.Num: lambda n: n.n,
            ast.Str: lambda n: n.s,
            ast.NameConstant: lambda n: n.value,
            ast.Name: self._eval_name,
            ast.Compare: self._eval_compare,
            ast.BoolOp: self._eval_boolop,
            ast.UnaryOp: self._eval_unaryop,
            ast.List: lambda n: [self._eval_node(elt) for elt in n.elts],
            ast.Tuple: lambda n: tuple(self._eval_node(elt) for elt in n.elts),
            ast.Set: lambda n: {self._eval_node(elt) for elt in n.elts},
            ast.Dict: lambda n: dict[str, Any](
                zip(
                    [self._eval_node(k) if k is not None else None for k in n.keys],
                    [self._eval_node(v) for v in n.values],
                    strict=False,
                )
            ),
        }
        handler = _DISPATCH.get(type(node))  # type: ignore[arg-type]
        if handler is None:
            raise ValueError(f"不支持的表达式类型: {type(node).__name__}")
        return handler(node)  # type: ignore[operator]

    def _eval_name(self, node: ast.Name) -> Any:
        """
        评估变量名引用.

        Args:
            node: Name 节点

        Returns:
            变量的值

        Raises:
            ValueError: 当变量名不在允许列表中时
        """
        name = node.id

        # 先检查内置常量
        if name in self._builtins:
            return self._builtins[name]

        # 再检查允许的变量名
        if name in self.allowed_names:
            return self.allowed_names[name]

        raise ValueError(f"未知的变量名: {name}")

    def _eval_compare(self, node: ast.Compare) -> bool:
        """
        评估比较表达式.

        支持链式比较,如: a < b < c

        Args:
            node: Compare 节点

        Returns:
            比较结果
        """
        left = self._eval_node(node.left)

        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self._eval_node(comparator)

            op_type = type(op)
            if op_type not in self.COMPARE_OPS:
                raise ValueError(f"不支持的比较运算符: {op_type.__name__}")

            op_func = self.COMPARE_OPS[op_type]
            if not op_func(left, right):
                return False

            left = right

        return True

    def _eval_boolop(self, node: ast.BoolOp) -> bool:
        """
        评估布尔运算表达式.

        Args:
            node: BoolOp 节点

        Returns:
            布尔运算结果
        """
        if isinstance(node.op, ast.And):
            return all(self._eval_node(value) for value in node.values)

        elif isinstance(node.op, ast.Or):
            return any(self._eval_node(value) for value in node.values)

        else:
            raise ValueError(f"不支持的布尔运算符: {type(node.op).__name__}")

    def _eval_unaryop(self, node: ast.UnaryOp) -> Any:
        """
        评估一元运算表达式.

        Args:
            node: UnaryOp 节点

        Returns:
            一元运算结果
        """
        operand = self._eval_node(node.operand)

        if isinstance(node.op, ast.Not):
            return not operand
        elif isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.UAdd):
            return +operand
        else:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")


def safe_eval(expression: str, allowed_names: dict[str, Any] | None = None) -> Any:
    """
    安全地评估表达式的便捷函数.

    Args:
        expression: 要评估的表达式字符串
        allowed_names: 允许在表达式中使用的变量名和值的映射

    Returns:
        表达式的评估结果

    Example:
        >>> safe_eval("x == 'production'", {"x": "production"})
        True
        >>> safe_eval("a > 10 and b < 20", {"a": 15, "b": 10})
        True
        >>> safe_eval("value in ['a', 'b', 'c']", {"value": "b"})
        True
    """
    evaluator = SafeExpressionEvaluator(allowed_names)
    return evaluator.evaluate(expression)
