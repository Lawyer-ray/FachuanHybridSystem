"""
Tests for core/config/ - schema, field, registry.
Also core/security/auth.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


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
        assert schema.validate_and_raise({"key": "value"}) is None  # Should not raise

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
        request.method = "GET"
        request.GET = {"token": "query_token"}

        mock_user = MagicMock()
        with patch.object(auth._jwt_auth, "authenticate", return_value=mock_user):
            result = auth(request)
            assert result is mock_user

    def test_token_from_query_param_head_allowed(self):
        """HEAD 与 GET 同为安全方法，允许 ?token=（下载/预览场景）。"""
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.method = "HEAD"
        request.GET = {"token": "query_token"}

        mock_user = MagicMock()
        with patch.object(auth._jwt_auth, "authenticate", return_value=mock_user):
            result = auth(request)
            assert result is mock_user

    def test_query_token_rejected_for_post(self):
        """POST 请求不得通过 ?token= 认证（query 参数会进访问日志，安全审计）。"""
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.method = "POST"
        request.GET = {"token": "query_token"}
        request.user.is_authenticated = False

        with patch.object(auth._jwt_auth, "authenticate", return_value=None) as mock_auth:
            result = auth(request)
            assert result is None
            # query token 未被送入 JWT 校验
            mock_auth.assert_not_called()

    def test_query_token_rejected_for_delete(self):
        from apps.core.security.auth import JWTOrSessionAuth

        auth = JWTOrSessionAuth()
        request = MagicMock()
        request.headers = {}
        request.method = "DELETE"
        request.GET = {"token": "query_token"}
        request.user.is_authenticated = False

        with patch.object(auth._jwt_auth, "authenticate", return_value=None) as mock_auth:
            assert auth(request) is None
            mock_auth.assert_not_called()

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
