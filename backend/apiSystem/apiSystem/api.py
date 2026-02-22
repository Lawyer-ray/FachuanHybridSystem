"""
API 主入口
统一注册所有路由和异常处理
支持 API 版本控制
"""

import json
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import NinjaAPI
from ninja.renderers import BaseRenderer
from ninja_jwt.routers.obtain import obtain_pair_router
from ninja_jwt.routers.verify import verify_router

from apps.core.auth import JWTOrSessionAuth
from apps.core.exceptions import register_exception_handlers
from apps.core.infrastructure import (  # type: ignore
    HealthChecker,
    ResourceUsage,
    get_resource_status,
    get_resource_usage,
    resource_monitor,
)
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.admin_access import ensure_admin_request

# API 版本号
API_VERSION = "1.0.0"


class UTF8JSONRenderer(BaseRenderer):
    """支持中文的 JSON 渲染器"""

    media_type = "application/json"

    def render(self, request: Any, data: Any, *, response_status: int) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)


# ============================================================
# API v1 实例
# ============================================================
api_v1 = NinjaAPI(
    title="法穿AI案件管理系统 API",
    version=API_VERSION,
    description="律师事务所案件、合同、客户管理系统",
    urls_namespace="api_v1",
    renderer=UTF8JSONRenderer(),
)

# 注册全局异常处理器
register_exception_handlers(api_v1)


def _register_app_routers() -> None:
    from apps.automation.api import router as automation_router
    from apps.cases.api import router as cases_router
    from apps.chat_records.api import router as chat_records_router
    from apps.client.api import router as client_router
    from apps.contracts.api import router as contracts_router
    from apps.core.api import router as config_router
    from apps.core.api.i18n_api import i18n_router
    from apps.core.api.ninja_llm_api import llm_router
    from apps.documents.api import (
        authorization_material_router,
        document_router,
        folder_template_router,
        generation_router,
        litigation_generation_router,
        placeholder_router,
        preservation_materials_router,
    )
    from apps.litigation_ai.api.litigation_api import router as ai_litigation_router
    from apps.organization.api import router as organization_router
    from apps.reminders.api import router as reminders_router

    api_v1.add_router("/config", config_router)
    api_v1.add_router("/llm", llm_router)
    api_v1.add_router("/i18n", i18n_router)
    api_v1.add_router("/organization", organization_router)
    api_v1.add_router("/client", client_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/cases", cases_router)
    api_v1.add_router("/contracts", contracts_router)
    api_v1.add_router("/automation", automation_router)
    api_v1.add_router("/reminders", reminders_router)
    api_v1.add_router("/chat-records", chat_records_router, tags=["梳理聊天记录"])

    api_v1.add_router("/documents", document_router, tags=["文件模板"])
    api_v1.add_router("/documents", folder_template_router, tags=["文件夹模板"])
    api_v1.add_router("/documents", placeholder_router, tags=["替换词"])
    api_v1.add_router("/documents", generation_router, tags=["文档生成"])
    api_v1.add_router("/documents", litigation_generation_router, tags=["诉讼文书生成"])
    api_v1.add_router("/documents", authorization_material_router, tags=["授权委托材料生成"])
    api_v1.add_router("/documents", preservation_materials_router, tags=["财产保全材料生成"])
    api_v1.add_router("/litigation", ai_litigation_router, tags=["AI 诉讼文书生成"])  # AI 诉讼文书生成


_register_app_routers()

# JWT 认证路由
api_v1.add_router("/token", router=obtain_pair_router, tags=["JWT认证"])
api_v1.add_router("/token", router=verify_router, tags=["JWT认证"])


# ============================================================
# 系统端点
# ============================================================


@api_v1.get("/", tags=["系统"])
def api_root(request: HttpRequest) -> dict[str, str]:
    """API 根路径，返回基本信息"""
    return {
        "message": "法律事务管理系统 API",
        "version": API_VERSION,
        "docs": "/api/v1/docs",
    }


@api_v1.get("/health", tags=["系统"])
def health_check(request: HttpRequest) -> dict[str, Any]:
    """
    健康检查端点
    返回系统整体健康状态
    """
    health = HealthChecker.get_system_health(include_details=False)
    return health.to_dict()  # type: ignore


@api_v1.get("/health/detail", tags=["系统"], auth=JWTOrSessionAuth())
def health_check_detail(request: HttpRequest) -> dict[str, Any]:
    """
    详细健康检查端点
    返回包含磁盘空间等详细信息的健康状态
    """
    ensure_admin_request(request, message="无权限访问健康检查详情", code="PERMISSION_DENIED")

    health = HealthChecker.get_system_health(include_details=True)
    return health.to_dict()  # type: ignore


@api_v1.get("/health/live", tags=["系统"])
def liveness_probe(request: HttpRequest) -> dict[str, Any]:
    """
    存活探针 (Kubernetes liveness probe)
    仅检查应用是否运行
    """
    return HealthChecker.liveness_check()  # type: ignore


@api_v1.get("/health/ready", tags=["系统"])
def readiness_probe(request: HttpRequest) -> dict[str, Any]:
    """
    就绪探针 (Kubernetes readiness probe)
    检查应用是否可以接收流量
    """
    return HealthChecker.readiness_check()  # type: ignore


# ============================================================
# 资源监控端点
# Requirements: 4.1, 4.2, 4.3, 4.4
# ============================================================


def _require_admin(request: HttpRequest) -> None:
    """检查当前用户是否为管理员，非管理员抛出 PermissionDenied"""
    ensure_admin_request(request, message="无权限访问资源监控", code="PERMISSION_DENIED")


@api_v1.get("/resource/status", tags=["资源监控"], auth=JWTOrSessionAuth())
def resource_status(request: HttpRequest) -> dict[str, Any]:
    """
    获取资源状态
    Requirements: 4.1, 4.2, 4.3, 4.4 - 资源监控和状态查询
    """
    _require_admin(request)
    return get_resource_status()  # type: ignore


@api_v1.get("/resource/usage", tags=["资源监控"], auth=JWTOrSessionAuth())
def resource_usage(request: HttpRequest) -> dict[str, Any]:
    """
    获取资源使用情况
    Requirements: 4.1, 4.2 - 资源使用情况查询
    """
    _require_admin(request)
    usage: ResourceUsage | None = get_resource_usage()
    if usage:
        return {
            "cpu_percent": usage.cpu_percent,
            "memory_percent": usage.memory_percent,
            "memory_used_mb": usage.memory_used_mb,
            "memory_total_mb": usage.memory_total_mb,
            "disk_percent": usage.disk_percent,
            "disk_used_gb": usage.disk_used_gb,
            "disk_total_gb": usage.disk_total_gb,
            "timestamp": usage.timestamp.isoformat(),
        }
    return {"error": "Resource monitoring not available"}


@api_v1.get("/resource/recommendations", tags=["资源监控"], auth=JWTOrSessionAuth())
def resource_recommendations(request: HttpRequest) -> dict[str, Any]:
    """
    获取资源优化建议
    Requirements: 4.1, 4.2 - 动态资源分配建议
    """
    _require_admin(request)
    return resource_monitor.get_resource_recommendations()


@api_v1.get("/resource/health", tags=["资源监控"], auth=JWTOrSessionAuth())
def resource_health(request: HttpRequest) -> dict[str, Any]:
    """
    资源健康检查（用于外部监控系统）
    Requirements: 4.3, 4.4 - 资源健康状态检查
    """
    _require_admin(request)
    return resource_monitor.check_resource_health()


@api_v1.get("/resource/metrics", tags=["资源监控"], auth=JWTOrSessionAuth())
@rate_limit_from_settings("EXPORT", by_user=True)
def resource_metrics(request: HttpRequest, window_minutes: int = 10, top: int = 10) -> dict[str, Any]:
    _require_admin(request)
    from apps.core.telemetry.metrics import snapshot

    return snapshot(window_minutes=int(window_minutes or 10), top=int(top or 10))


@api_v1.get("/resource/metrics/prometheus", tags=["资源监控"], auth=JWTOrSessionAuth())
@rate_limit_from_settings("EXPORT", by_user=True)
def resource_metrics_prometheus(request: HttpRequest, window_minutes: int = 10) -> HttpResponse:
    _require_admin(request)
    from apps.core.telemetry.metrics import snapshot_prometheus

    payload = snapshot_prometheus(window_minutes=int(window_minutes or 10))
    return HttpResponse(payload, content_type="text/plain; version=0.0.4; charset=utf-8")


# 兼容性别名
api = api_v1
