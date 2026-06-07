"""Coverage tests for core.config.validators.safe_expression_evaluator."""

import pytest

from apps.core.config.validators.safe_expression_evaluator import SafeExpressionEvaluator, safe_eval


class TestSafeExpressionEvaluator:
    def test_constant_int(self):
        assert safe_eval("42", {}) == 42

    def test_constant_string(self):
        assert safe_eval("'hello'", {}) == "hello"

    def test_constant_bool(self):
        assert safe_eval("True", {}) is True
        assert safe_eval("False", {}) is False
        assert safe_eval("None", {}) is None

    def test_variable_lookup(self):
        assert safe_eval("x", {"x": 10}) == 10

    def test_unknown_variable(self):
        with pytest.raises(ValueError, match="未知变量"):
            safe_eval("unknown", {})

    def test_comparison_eq(self):
        assert safe_eval("x == 5", {"x": 5}) is True
        assert safe_eval("x == 3", {"x": 5}) is False

    def test_comparison_ne(self):
        assert safe_eval("x != 3", {"x": 5}) is True

    def test_comparison_lt(self):
        assert safe_eval("x < 10", {"x": 5}) is True

    def test_comparison_gt(self):
        assert safe_eval("x > 3", {"x": 5}) is True

    def test_comparison_lte(self):
        assert safe_eval("x <= 5", {"x": 5}) is True

    def test_comparison_gte(self):
        assert safe_eval("x >= 5", {"x": 5}) is True

    def test_comparison_in(self):
        assert safe_eval("x in y", {"x": 1, "y": [1, 2, 3]}) is True

    def test_comparison_not_in(self):
        assert safe_eval("x not in y", {"x": 5, "y": [1, 2, 3]}) is True

    def test_bool_and(self):
        assert safe_eval("True and True", {}) is True
        assert safe_eval("True and False", {}) is False

    def test_bool_or(self):
        assert safe_eval("False or True", {}) is True
        assert safe_eval("False or False", {}) is False

    def test_unary_not(self):
        assert safe_eval("not False", {}) is True

    def test_unary_neg(self):
        assert safe_eval("-x", {"x": 5}) == -5

    def test_unary_pos(self):
        assert safe_eval("+x", {"x": 5}) == 5

    def test_list_literal(self):
        assert safe_eval("[1, 2, 3]", {}) == [1, 2, 3]

    def test_tuple_literal(self):
        assert safe_eval("(1, 2)", {}) == (1, 2)

    def test_dict_literal(self):
        result = safe_eval("{'a': 1}", {})
        assert result == {"a": 1}

    def test_syntax_error(self):
        with pytest.raises(SyntaxError):
            safe_eval("1 ++ ", {})

    def test_unsupported_node(self):
        with pytest.raises(ValueError, match="不支持"):
            safe_eval("lambda x: x", {})

    def test_complex_expression(self):
        assert safe_eval("x > 0 and x < 10", {"x": 5}) is True

    def test_chained_comparison(self):
        assert safe_eval("1 < x < 10", {"x": 5}) is True

    def test_is_comparison(self):
        result = safe_eval("x is None", {"x": None})
        assert result is True

    def test_is_not_comparison(self):
        result = safe_eval("x is not None", {"x": 42})
        assert result is True
