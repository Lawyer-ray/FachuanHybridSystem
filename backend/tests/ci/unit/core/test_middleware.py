"""测试 core.middleware 子模块

覆盖: security.py (SecurityHeadersMiddleware, PermissionsPolicyMiddleware, ServiceLocatorScopeMiddleware)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ============================================================
# SecurityHeadersMiddleware
# ============================================================


class TestSecurityHeadersMiddleware:
    """测试 SecurityHeadersMiddleware"""

    def _make_middleware(self, **settings_attrs: object):
        from apps.core.middleware.security import SecurityHeadersMiddleware

        mock_settings = SimpleNamespace(**settings_attrs)

        def get_response(request):  # type: ignore[no-untyped-def]
            from django.http import HttpResponse

            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            return SecurityHeadersMiddleware(get_response), mock_settings

    def test_api_path_sets_csp(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import SecurityHeadersMiddleware

        settings_attrs = {
            "CONTENT_SECURITY_POLICY_API": "default-src 'self'",
            "CONTENT_SECURITY_POLICY_API_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY": "",
            "CONTENT_SECURITY_POLICY_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY_ADMIN": "",
            "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY": "",
        }
        mock_settings = SimpleNamespace(**settings_attrs)

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = SecurityHeadersMiddleware(get_response)
            request = HttpRequest()
            request.path = "/api/v1/cases"
            response = mw(request)
            assert response.get("Content-Security-Policy") == "default-src 'self'"

    def test_admin_path_sets_admin_csp(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import SecurityHeadersMiddleware

        settings_attrs = {
            "CONTENT_SECURITY_POLICY_API": "",
            "CONTENT_SECURITY_POLICY_API_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY": "",
            "CONTENT_SECURITY_POLICY_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY_ADMIN": "admin-csp-value",
            "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY": "",
        }
        mock_settings = SimpleNamespace(**settings_attrs)

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = SecurityHeadersMiddleware(get_response)
            request = HttpRequest()
            request.path = "/admin/dashboard"
            response = mw(request)
            assert response.get("Content-Security-Policy") == "admin-csp-value"

    def test_docs_path_uses_default_csp(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import SecurityHeadersMiddleware

        settings_attrs = {
            "CONTENT_SECURITY_POLICY_API": "api-csp",
            "CONTENT_SECURITY_POLICY_API_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY": "default-csp",
            "CONTENT_SECURITY_POLICY_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY_ADMIN": "",
            "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY": "",
        }
        mock_settings = SimpleNamespace(**settings_attrs)

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = SecurityHeadersMiddleware(get_response)
            request = HttpRequest()
            request.path = "/api/v1/docs"
            response = mw(request)
            # /docs 路径使用默认策略而不是 API 策略
            assert response.get("Content-Security-Policy") == "default-csp"

    def test_no_csp_when_empty(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import SecurityHeadersMiddleware

        settings_attrs = {
            "CONTENT_SECURITY_POLICY_API": "",
            "CONTENT_SECURITY_POLICY_API_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY": "",
            "CONTENT_SECURITY_POLICY_REPORT_ONLY": "",
            "CONTENT_SECURITY_POLICY_ADMIN": "",
            "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY": "",
        }
        mock_settings = SimpleNamespace(**settings_attrs)

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = SecurityHeadersMiddleware(get_response)
            request = HttpRequest()
            request.path = "/api/v1/test"
            response = mw(request)
            assert "Content-Security-Policy" not in response


# ============================================================
# PermissionsPolicyMiddleware
# ============================================================


class TestPermissionsPolicyMiddleware:
    """测试 PermissionsPolicyMiddleware"""

    def test_string_policy(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mock_settings = SimpleNamespace(PERMISSIONS_POLICY="geolocation=(), camera=()")

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = PermissionsPolicyMiddleware(get_response)
            request = HttpRequest()
            request.path = "/"
            response = mw(request)
            assert response.get("Permissions-Policy") == "geolocation=(), camera=()"

    def test_dict_policy(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mock_settings = SimpleNamespace(
            PERMISSIONS_POLICY={"geolocation": [], "camera": "*"}
        )

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = PermissionsPolicyMiddleware(get_response)
            request = HttpRequest()
            request.path = "/"
            response = mw(request)
            policy = response.get("Permissions-Policy", "")
            assert "geolocation=()" in policy
            assert "camera=*" in policy

    def test_no_policy(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mock_settings = SimpleNamespace(PERMISSIONS_POLICY="")

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = PermissionsPolicyMiddleware(get_response)
            request = HttpRequest()
            request.path = "/"
            response = mw(request)
            assert "Permissions-Policy" not in response

    def test_serialize_allowlist_empty(self) -> None:
        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mw = PermissionsPolicyMiddleware(lambda r: None)  # type: ignore[arg-type]
        assert mw._serialize_allowlist(None) == "()"
        assert mw._serialize_allowlist([]) == "()"
        assert mw._serialize_allowlist(()) == "()"

    def test_serialize_allowlist_wildcard(self) -> None:
        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mw = PermissionsPolicyMiddleware(lambda r: None)  # type: ignore[arg-type]
        assert mw._serialize_allowlist("*") == "*"

    def test_serialize_allowlist_self(self) -> None:
        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mw = PermissionsPolicyMiddleware(lambda r: None)  # type: ignore[arg-type]
        result = mw._serialize_allowlist(["self"])
        assert "self" in result

    def test_serialize_source_values(self) -> None:
        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mw = PermissionsPolicyMiddleware(lambda r: None)  # type: ignore[arg-type]
        assert mw._serialize_source("self") == "self"
        assert mw._serialize_source("src") == "src"
        assert mw._serialize_source("*") == "*"
        assert mw._serialize_source("https://example.com") == '"https://example.com"'

    def test_dict_policy_with_strings(self) -> None:
        from django.http import HttpRequest, HttpResponse

        from apps.core.middleware.security import PermissionsPolicyMiddleware

        mock_settings = SimpleNamespace(
            PERMISSIONS_POLICY={"geolocation": "self"}
        )

        def get_response(request):  # type: ignore[no-untyped-def]
            return HttpResponse("ok")

        with patch("apps.core.middleware.security.settings", mock_settings):
            mw = PermissionsPolicyMiddleware(get_response)
            request = HttpRequest()
            request.path = "/"
            response = mw(request)
            policy = response.get("Permissions-Policy", "")
            assert "geolocation=" in policy
            assert "self" in policy
