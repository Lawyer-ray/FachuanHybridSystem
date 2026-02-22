"""
组织访问控制中间件
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from apps.core.cache import CacheKeys, CacheTimeout
from .services.wiring import build_org_access_computation_service


class OrgAccessMiddleware(MiddlewareMixin):
    """
    组织访问权限中间件
    为每个请求计算用户的访问权限范围，并缓存结果
    """

    def process_request(self, request: HttpRequest) -> None:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        # 尝试从缓存获取
        cache_key = CacheKeys.user_org_access(user.id)
        org_access = cache.get(cache_key)

        if org_access is None:
            org_access = self._compute_org_access(user)
            cache.set(cache_key, org_access, CacheTimeout.MEDIUM)

        request.org_access = org_access  # type: ignore[attr-defined]
        request.perm_open_access = bool(getattr(settings, "PERM_OPEN_ACCESS", False))  # type: ignore[attr-defined]
        return None

    def _compute_org_access(self, user: Any) -> dict[str, Any]:
        """
        计算用户的组织访问权限
        委托给 OrgAccessComputationService 处理
        """
        service = build_org_access_computation_service()
        return service.compute(user)


class ApiTrailingSlashMiddleware(MiddlewareMixin):
    """
    API 尾部斜杠处理中间件
    移除 API 路径末尾的斜杠，保持 URL 一致性
    """

    def process_request(self, request: HttpRequest) -> None:
        path = request.path_info or ""
        if path.startswith("/api/") and path != "/api/" and path.endswith("/"):
            request.path_info = path.rstrip("/")
        return None


def invalidate_user_org_cache(user_id: int) -> None:
    """
    使用户组织权限缓存失效
    在用户团队变更时调用

    Args:
        user_id: 用户 ID
    """
    cache.delete(CacheKeys.user_org_access(user_id))


def invalidate_case_access_cache(user_id: int) -> None:
    """
    使用户案件访问授权缓存失效
    在案件授权变更时调用

    Args:
        user_id: 用户 ID
    """
    cache.delete(CacheKeys.user_org_access(user_id))
