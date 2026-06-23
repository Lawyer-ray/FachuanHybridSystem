"""Coverage tests for organization/middleware.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse


class TestOrgAccessMiddleware:
    def test_unauthenticated_user_skipped(self) -> None:
        from apps.organization.middleware import OrgAccessMiddleware

        sentinel = HttpResponse()
        middleware = OrgAccessMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.user = MagicMock()
        request.user.is_authenticated = False
        result = middleware(request)
        assert result is sentinel

    def test_no_user_skipped(self) -> None:
        from apps.organization.middleware import OrgAccessMiddleware

        sentinel = HttpResponse()
        middleware = OrgAccessMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.user = None
        result = middleware(request)
        assert result is sentinel

    def test_authenticated_user_sets_org_access(self) -> None:
        from apps.organization.middleware import OrgAccessMiddleware

        sentinel = HttpResponse()
        middleware = OrgAccessMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.id = 42

        with (
            patch("apps.organization.middleware.cache") as mock_cache,
            patch("apps.organization.middleware.build_org_access_computation_service") as mock_build,
            patch("apps.organization.middleware.settings") as mock_settings,
        ):
            mock_cache.get.return_value = None
            mock_build.return_value.compute.return_value = {"org_ids": [1]}
            mock_settings.PERM_OPEN_ACCESS = False
            result = middleware(request)
            assert request.org_access == {"org_ids": [1]}
            assert request.perm_open_access is False
            assert result is sentinel

    def test_cached_org_access(self) -> None:
        from apps.organization.middleware import OrgAccessMiddleware

        sentinel = HttpResponse()
        middleware = OrgAccessMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.id = 42

        with (
            patch("apps.organization.middleware.cache") as mock_cache,
            patch("apps.organization.middleware.settings") as mock_settings,
        ):
            mock_cache.get.return_value = {"org_ids": [1]}
            mock_settings.PERM_OPEN_ACCESS = True
            result = middleware(request)
            assert request.org_access == {"org_ids": [1]}
            assert request.perm_open_access is True
            assert result is sentinel


class TestApiTrailingSlashMiddleware:
    def test_strips_trailing_slash_for_api(self) -> None:
        from apps.organization.middleware import ApiTrailingSlashMiddleware

        sentinel = HttpResponse()
        middleware = ApiTrailingSlashMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.path_info = "/api/v1/cases/"
        middleware(request)
        assert request.path_info == "/api/v1/cases"

    def test_preserves_api_root_slash(self) -> None:
        from apps.organization.middleware import ApiTrailingSlashMiddleware

        sentinel = HttpResponse()
        middleware = ApiTrailingSlashMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.path_info = "/api/"
        middleware(request)
        assert request.path_info == "/api/"

    def test_ignores_non_api_paths(self) -> None:
        from apps.organization.middleware import ApiTrailingSlashMiddleware

        sentinel = HttpResponse()
        middleware = ApiTrailingSlashMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.path_info = "/admin/cases/"
        middleware(request)
        assert request.path_info == "/admin/cases/"

    def test_no_trailing_slash_unchanged(self) -> None:
        from apps.organization.middleware import ApiTrailingSlashMiddleware

        sentinel = HttpResponse()
        middleware = ApiTrailingSlashMiddleware(lambda r: sentinel)
        request = MagicMock(spec=HttpRequest)
        request.path_info = "/api/v1/cases"
        middleware(request)
        assert request.path_info == "/api/v1/cases"


class TestInvalidateUserOrgCache:
    def test_invalidate_calls_cache_delete(self) -> None:
        from apps.organization.middleware import invalidate_user_org_cache

        with patch("apps.organization.middleware.cache") as mock_cache:
            invalidate_user_org_cache(42)
            mock_cache.delete.assert_called_once()
