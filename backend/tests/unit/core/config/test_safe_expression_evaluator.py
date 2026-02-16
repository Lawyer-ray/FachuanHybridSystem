import pytest

from apps.core.config.validators.safe_expression_evaluator import SafeExpressionEvaluator, safe_eval


def test_safe_eval_basic_compare() -> None:
    assert safe_eval("x == 'production'", {"x": "production"}) is True
    assert safe_eval("x != 'production'", {"x": "staging"}) is True


def test_safe_eval_bool_ops() -> None:
    evaluator = SafeExpressionEvaluator({"a": 15, "b": 10})
    assert evaluator.evaluate("a > 10 and b < 20") is True
    assert evaluator.evaluate("a > 10 and b > 20") is False
    assert evaluator.evaluate("a < 10 or b < 20") is True


def test_safe_eval_in_not_in() -> None:
    assert safe_eval("value in ['a', 'b', 'c']", {"value": "b"}) is True
    assert safe_eval("value not in ('a', 'b')", {"value": "c"}) is True


def test_safe_eval_literals_and_unary_ops() -> None:
    evaluator = SafeExpressionEvaluator({"x": 1})
    assert evaluator.evaluate("-x < 0") is True
    assert evaluator.evaluate("+x == 1") is True
    assert evaluator.evaluate("not False") is True
    assert evaluator.evaluate("True and (None is None)") is True
    assert evaluator.evaluate("{'a': 1, None: 2}") == {"a": 1, None: 2}
    assert evaluator.evaluate("{'a', 'b'}") == {"a", "b"}
    assert evaluator.evaluate("(1, 2, 3)") == (1, 2, 3)


def test_safe_eval_chain_compare_and_is_ops() -> None:
    evaluator = SafeExpressionEvaluator({"x": 2, "y": 2})
    assert evaluator.evaluate("1 < x < 3") is True
    assert evaluator.evaluate("x is y") is True
    assert evaluator.evaluate("x is not 3") is True


def test_safe_eval_syntax_error_is_wrapped() -> None:
    evaluator = SafeExpressionEvaluator({"x": 1})
    with pytest.raises(SyntaxError) as exc:
        evaluator.evaluate("x ==")
    assert "表达式语法错误" in str(exc.value)


def test_safe_eval_unsupported_unary_op_rejected() -> None:
    evaluator = SafeExpressionEvaluator({})
    with pytest.raises(ValueError):
        evaluator.evaluate("~1")


def test_safe_eval_unknown_name_rejected() -> None:
    evaluator = SafeExpressionEvaluator({})
    with pytest.raises(ValueError):
        evaluator.evaluate("missing == 1")


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo pwned')",
        "open('x', 'w')",
        "x.__class__",
        "x[0]",
        "(lambda: 1)()",
    ],
)
def test_safe_eval_unsupported_syntax_rejected(expr: str) -> None:
    evaluator = SafeExpressionEvaluator({"x": [1, 2, 3]})
    with pytest.raises(ValueError):
        evaluator.evaluate(expr)


def test_safe_eval_unsupported_expression_node_rejected() -> None:
    evaluator = SafeExpressionEvaluator({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        evaluator.evaluate("a + b")
