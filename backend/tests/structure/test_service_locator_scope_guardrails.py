from __future__ import annotations


def test_service_locator_scope_middleware_enabled_by_default():
    from django.conf import settings

    assert "apps.core.middleware.ServiceLocatorScopeMiddleware" in settings.MIDDLEWARE
