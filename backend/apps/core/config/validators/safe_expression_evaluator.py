"""安全表达式求值器，仅支持比较、布尔运算等受限语法，禁止任意代码执行。"""

from __future__ import annotations

import ast
from typing import Any


class SafeExpressionEvaluator:
    """基于 AST 白名单的安全表达式求值器。"""

    _ALLOWED_UNARY: tuple[type[ast.unaryop], ...] = (ast.UAdd, ast.USub, ast.Not)

    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context

    def evaluate(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise SyntaxError(f"表达式语法错误: {e}") from e
        return self._eval(tree.body)

    def _eval(self, node: ast.expr) -> Any:  # type: ignore[return]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[node.id]
            if node.id not in self._context:
                raise ValueError(f"未知变量: {node.id!r}")
            return self._context[node.id]
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, self._ALLOWED_UNARY):
                raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
            operand = self._eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand  # type: ignore[operator]
            if isinstance(node.op, ast.USub):
                return -operand  # type: ignore[operator]
            return not operand
        if isinstance(node, ast.BoolOp):
            values = [self._eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                result: Any = True
                for v in values:
                    result = result and v
                return result
            result = False
            for v in values:
                result = result or v
            return result
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)
                if not self._compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elts = [self._eval(e) for e in node.elts]
            if isinstance(node, ast.List):
                return elts
            if isinstance(node, ast.Tuple):
                return tuple(elts)
            return set(elts)
        if isinstance(node, ast.Dict):
            return {self._eval(k): self._eval(v) for k, v in zip(node.keys, node.values) if k is not None}
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    @staticmethod
    def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return bool(left == right)
        if isinstance(op, ast.NotEq):
            return bool(left != right)
        if isinstance(op, ast.Lt):
            return bool(left < right)
        if isinstance(op, ast.LtE):
            return bool(left <= right)
        if isinstance(op, ast.Gt):
            return bool(left > right)
        if isinstance(op, ast.GtE):
            return bool(left >= right)
        if isinstance(op, ast.In):
            return bool(left in right)
        if isinstance(op, ast.NotIn):
            return bool(left not in right)
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        raise ValueError(f"不支持的比较运算符: {type(op).__name__}")


def safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """便捷函数：对给定上下文安全求值表达式。"""
    return SafeExpressionEvaluator(context).evaluate(expr)
