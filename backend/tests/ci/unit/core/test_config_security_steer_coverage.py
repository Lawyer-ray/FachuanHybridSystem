"""
Tests for core/config/ - schema, field, safe_expression_evaluator, registry, steering modules.
Also core/security/auth.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


class TestSafeExpressionEvaluator:
    def test_constant(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("42", {}) == 42
        assert safe_eval("'hello'", {}) == "hello"
        assert safe_eval("True", {}) is True
        assert safe_eval("None", {}) is None

    def test_variable_lookup(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("x", {"x": 10}) == 10

    def test_unknown_variable_raises(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        with pytest.raises(ValueError, match="未知变量"):
            safe_eval("unknown_var", {})

    def test_comparison(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("x > 5", {"x": 10}) is True
        assert safe_eval("x < 5", {"x": 10}) is False
        assert safe_eval("x == 10", {"x": 10}) is True
        assert safe_eval("x != 10", {"x": 10}) is False
        assert safe_eval("x >= 10", {"x": 10}) is True
        assert safe_eval("x <= 10", {"x": 10}) is True

    def test_boolean_ops(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("True and False", {}) is False
        assert safe_eval("True or False", {}) is True

    def test_unary_ops(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("not True", {}) is False
        assert safe_eval("-5", {}) == -5
        assert safe_eval("+5", {}) == 5

    def test_in_not_in(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("x in [1, 2, 3]", {"x": 2}) is True
        assert safe_eval("x not in [1, 2, 3]", {"x": 5}) is True

    def test_is_is_not(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("x is None", {"x": None}) is True
        assert safe_eval("x is not None", {"x": 5}) is True

    def test_list_tuple_set(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("[1, 2, 3]", {}) == [1, 2, 3]
        result = safe_eval("(1, 2)", {})
        assert result == (1, 2)
        result = safe_eval("{1, 2}", {})
        assert result == {1, 2}

    def test_dict(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        result = safe_eval("{'a': 1, 'b': 2}", {})
        assert result == {"a": 1, "b": 2}

    def test_syntax_error_raises(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        with pytest.raises(SyntaxError, match="语法错误"):
            safe_eval("invalid syntax !@#", {})

    def test_unsupported_node_raises(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        with pytest.raises(ValueError, match="不支持"):
            safe_eval("lambda x: x", {})

    def test_chained_comparison(self):
        from apps.core.config.validators.safe_expression_evaluator import safe_eval

        assert safe_eval("1 < x < 10", {"x": 5}) is True
        assert safe_eval("1 < x < 10", {"x": 15}) is False


class TestConfigField:
    def test_basic_field(self):
        from apps.core.config.schema.field import ConfigField

        field = ConfigField(name="test", type=str, default="value")
        assert field.name == "test"
        assert field.default == "value"

    def test_min_max_value_validation(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="min_value"):
            ConfigField(name="bad", type=int, min_value=10, max_value=5)

    def test_min_max_length_validation(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="min_length"):
            ConfigField(name="bad", type=str, min_length=10, max_length=5)

    def test_required_with_default_raises(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="必需字段"):
            ConfigField(name="bad", type=str, required=True, default="val")


class TestConfigSchema:
    def test_register_and_get(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        field = ConfigField(name="my_key", type=str, default="val")
        schema.register(field)
        assert schema.get_field("my_key") is field

    def test_duplicate_register_raises(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        field = ConfigField(name="dup", type=str)
        schema.register(field)
        with pytest.raises(ValueError, match="已存在"):
            schema.register(field)

    def test_get_nonexistent_returns_none(self):
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        assert schema.get_field("nonexistent") is None

    def test_validate_and_raise_missing_required(self):
        from apps.core.config.exceptions import ConfigValidationError
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="required_key", type=str, required=True))
        with pytest.raises(ConfigValidationError):
            schema.validate_and_raise({})

    def test_validate_passes_when_present(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="key", type=str, required=True))
        schema.validate_and_raise({"key": "value"})  # Should not raise

    def test_get_suggestions_exact(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="database.url", type=str))
        schema.register(ConfigField(name="database.name", type=str))
        suggestions = schema.get_suggestions("database.url")
        assert "database.url" in suggestions

    def test_get_suggestions_partial(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="llm.model", type=str))
        schema.register(ConfigField(name="llm.timeout", type=int))
        schema.register(ConfigField(name="app.name", type=str))
        suggestions = schema.get_suggestions("llm")
        assert len(suggestions) >= 2


class TestConfigRegistry:
    def test_registry_is_dict(self):
        from apps.core.config.schema.registry import CONFIG_REGISTRY

        assert isinstance(CONFIG_REGISTRY, dict)

    def test_registry_has_fields(self):
        from apps.core.config.schema.registry import CONFIG_REGISTRY

        assert len(CONFIG_REGISTRY) > 0
        for key, field in CONFIG_REGISTRY.items():
            assert hasattr(field, "name")
            assert field.name == key


class TestSteeringPerfModels:
    def test_performance_metric(self):
        from apps.core.config.steering._perf_models import PerformanceMetric

        metric = PerformanceMetric(name="test_metric", value=42.0, unit="ms", timestamp=1.0)
        assert metric.name == "test_metric"
        assert metric.value == 42.0

    def test_alert_level_enum(self):
        from apps.core.config.steering._perf_models import AlertLevel

        assert AlertLevel.INFO is not None
        assert AlertLevel.WARNING is not None

    def test_performance_thresholds(self):
        from apps.core.config.steering._perf_models import PerformanceThresholds

        thresholds = PerformanceThresholds(config={"warn_ms": 100, "error_ms": 500})
        assert thresholds is not None


class TestSessionAuth:
    def test_authenticate_authenticated_user(self):
        from apps.core.security.auth import SessionAuth

        auth = SessionAuth()
        request = MagicMock()
        request.user.is_authenticated = True
        result = auth.authenticate(request, "any_key")
        assert result is request.user

    def test_authenticate_anonymous_user(self):
        from apps.core.security.auth import SessionAuth

        auth = SessionAuth()
        request = MagicMock()
        request.user.is_authenticated = False
        result = auth.authenticate(request, "any_key")
        assert result is None


class TestJWTOrSessionAuth:
    def test_jwt_auth_success(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {"Authorization": "Bearer valid_token"}
        request.GET = {}

        mock_user = MagicMock()
        with patch.object(auth._jwt_auth, "authenticate", return_value=mock_user):
            result = auth(request)
            assert result is mock_user

    def test_session_auth_fallback(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.GET = {}
        request.method = "GET"
        request.user.is_authenticated = True

        with patch.object(auth._jwt_auth, "authenticate", return_value=None):
            result = auth(request)
            assert result is request.user

    def test_no_auth_returns_none(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.GET = {}
        request.user.is_authenticated = False

        with patch.object(auth._jwt_auth, "authenticate", return_value=None):
            result = auth(request)
            assert result is None

    def test_token_from_query_param(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.GET = {"token": "query_token"}

        mock_user = MagicMock()
        with patch.object(auth._jwt_auth, "authenticate", return_value=mock_user):
            result = auth(request)
            assert result is mock_user

    def test_jwt_error_with_debug(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {"Authorization": "Bearer bad_token"}
        request.GET = {}
        request.method = "GET"
        request.user.is_authenticated = True

        with patch.object(auth._jwt_auth, "authenticate", side_effect=RuntimeError("jwt error")):
            with patch("apps.core.security.auth.settings") as mock_settings:
                mock_settings.DEBUG = True
                result = auth(request)
                # Should fall back to session auth
                assert result is request.user

    def test_session_csrf_check(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.GET = {}
        request.method = "POST"
        request.user.is_authenticated = True

        with patch.object(auth._jwt_auth, "authenticate", return_value=None):
            with patch("apps.core.security.auth.CsrfViewMiddleware") as mock_csrf:
                mock_middleware_instance = MagicMock()
                mock_middleware_instance.process_view.return_value = MagicMock()  # CSRF fails
                mock_csrf.return_value = mock_middleware_instance
                with pytest.raises(Exception):  # PermissionDenied
                    auth(request)

    def test_authenticate_delegates_to_call(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.GET = {}
        request.user.is_authenticated = False

        with patch.object(auth._jwt_auth, "authenticate", return_value=None):
            result = auth.authenticate(request, "token")
            assert result is None


