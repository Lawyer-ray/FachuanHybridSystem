"""安全表达式求值器，仅支持比较、布尔运算等受限语法，禁止任意代码执行。"""

from __future__ import annotations

import ast
from typing import Any

_UNARY_OPS: dict[type[ast.unaryop], str] = {
    ast.UAdd: "uadd",
    ast.USub: "usub",
    ast.Not: "not",
}

_CMP_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "le",
    ast.Gt: "gt",
    ast.GtE: "ge",
    ast.In: "in",
    ast.NotIn: "not_in",
    ast.Is: "is",
    ast.IsNot: "is_not",
}


class SafeExpressionEvaluator:
    """基于 AST 白名单的安全表达式求值器。"""

    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context

    def evaluate(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise SyntaxError(f"表达式语法错误: {e}") from e
        return self._eval(tree.body)

    def _eval(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self._eval_name(node)
        if isinstance(node, ast.UnaryOp):
            return self._eval_unary(node)
        if isinstance(node, ast.BoolOp):
            return self._eval_bool(node)
        if isinstance(node, ast.Compare):
            return self._eval_compare(node)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return self._eval_sequence(node)
        if isinstance(node, ast.Dict):
            return self._eval_dict(node)
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    def _eval_name(self, node: ast.Name) -> Any:
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        if node.id not in self._context:
            raise ValueError(f"未知变量: {node.id!r}")
        return self._context[node.id]

    def _eval_unary(self, node: ast.UnaryOp) -> Any:
        op_key = type(node.op)
        if op_key not in _UNARY_OPS:
            raise ValueError(f"不支持的一元运算符: {op_key.__name__}")
        operand = self._eval(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        return not operand

    def _eval_bool(self, node: ast.BoolOp) -> Any:
        values = [self._eval(v) for v in node.values]
        result: Any = isinstance(node.op, ast.And)
        for v in values:
            result = (result and v) if isinstance(node.op, ast.And) else (result or v)
        return result

    def _eval_compare(self, node: ast.Compare) -> bool:
        left = self._eval(node.left)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self._eval(comparator)
            if not _apply_cmp(op, left, right):
                return False
            left = right
        return True

    def _eval_sequence(self, node: ast.List | ast.Tuple | ast.Set) -> Any:
        elts = [self._eval(e) for e in node.elts]
        if isinstance(node, ast.List):
            return elts
        if isinstance(node, ast.Tuple):
            return tuple(elts)
        return set(elts)

    def _eval_dict(self, node: ast.Dict) -> dict[Any, Any]:
        return {self._eval(k): self._eval(v) for k, v in zip(node.keys, node.values, strict=False) if k is not None}


def _apply_cmp(op: ast.cmpop, left: Any, right: Any) -> bool:
    op_key = type(op)
    if op_key not in _CMP_OPS:
        raise ValueError(f"不支持的比较运算符: {op_key.__name__}")
    return _CMP_FUNCS[op_key](left, right)  # type: ignore[no-any-return]


_CMP_FUNCS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda l, r: l == r,
    ast.NotEq: lambda l, r: l != r,
    ast.Lt: lambda l, r: l < r,
    ast.LtE: lambda l, r: l <= r,
    ast.Gt: lambda l, r: l > r,
    ast.GtE: lambda l, r: l >= r,
    ast.In: lambda l, r: l in r,
    ast.NotIn: lambda l, r: l not in r,
    ast.Is: lambda l, r: l is r,
    ast.IsNot: lambda l, r: l is not r,
}


def safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """便捷函数：对给定上下文安全求值表达式。"""
    return SafeExpressionEvaluator(context).evaluate(expr)
