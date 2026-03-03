"""
组织访问控制中间件
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from apps.core.infrastructure.cache import CacheKeys, CacheTimeout
from apps.organization.models import Lawyer

from .services.wiring import build_org_access_computation_service


class OrgAccessMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> None:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        cache_key = CacheKeys.user_org_access(user.id)
        org_access = cache.get(cache_key)

        if org_access is None:
            org_access = build_org_access_computation_service().compute(user)
            cache.set(cache_key, org_access, CacheTimeout.MEDIUM)

        request.org_access = org_access  # type: ignore[attr-defined]
        request.perm_open_access = bool(getattr(settings, "PERM_OPEN_ACCESS", False))  # type: ignore[attr-defined]
        return None


class ApiTrailingSlashMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> None:
        path = request.path_info or ""
        if path.startswith("/api/") and path != "/api/" and path.endswith("/"):
            request.path_info = path.rstrip("/")
        return None


def invalidate_user_org_cache(user_id: int) -> None:
    cache.delete(CacheKeys.user_org_access(user_id))
