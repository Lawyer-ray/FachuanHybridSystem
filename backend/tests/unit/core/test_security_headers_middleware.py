import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import SecurityHeadersMiddleware


@pytest.mark.unit
def test_security_headers_middleware_uses_api_policy_for_api_endpoints(settings):
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = "g-ro"
    settings.CONTENT_SECURITY_POLICY = "g"
    settings.CONTENT_SECURITY_POLICY_API_REPORT_ONLY = "api-ro"
    settings.CONTENT_SECURITY_POLICY_API = "api"
    settings.CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY = "admin-ro"
    settings.CONTENT_SECURITY_POLICY_ADMIN = "admin"

    rf = RequestFactory()
    request = rf.get("/api/v1/cases")

    middleware = SecurityHeadersMiddleware(lambda _req: HttpResponse("ok"))
    response = middleware(request)
    assert response["Content-Security-Policy"] == "api"
    assert response["Content-Security-Policy-Report-Only"] == "api-ro"


@pytest.mark.unit
def test_security_headers_middleware_uses_admin_policy_for_admin(settings):
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = "g-ro"
    settings.CONTENT_SECURITY_POLICY = "g"
    settings.CONTENT_SECURITY_POLICY_API_REPORT_ONLY = "api-ro"
    settings.CONTENT_SECURITY_POLICY_API = "api"
    settings.CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY = "admin-ro"
    settings.CONTENT_SECURITY_POLICY_ADMIN = "admin"

    rf = RequestFactory()
    request = rf.get("/admin/login/")

    middleware = SecurityHeadersMiddleware(lambda _req: HttpResponse("ok"))
    response = middleware(request)
    assert response["Content-Security-Policy"] == "admin"
    assert response["Content-Security-Policy-Report-Only"] == "admin-ro"


@pytest.mark.unit
def test_security_headers_middleware_does_not_apply_api_policy_to_docs(settings):
    settings.CONTENT_SECURITY_POLICY_REPORT_ONLY = "g-ro"
    settings.CONTENT_SECURITY_POLICY = "g"
    settings.CONTENT_SECURITY_POLICY_API_REPORT_ONLY = "api-ro"
    settings.CONTENT_SECURITY_POLICY_API = "api"
    settings.CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY = ""
    settings.CONTENT_SECURITY_POLICY_ADMIN = ""

    rf = RequestFactory()
    request = rf.get("/api/v1/docs")

    middleware = SecurityHeadersMiddleware(lambda _req: HttpResponse("ok"))
    response = middleware(request)
    assert response["Content-Security-Policy"] == "g"
    assert response["Content-Security-Policy-Report-Only"] == "g-ro"
