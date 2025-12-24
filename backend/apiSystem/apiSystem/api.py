"""
API 主入口
统一注册所有路由和异常处理
支持 API 版本控制
"""
from ninja import NinjaAPI
from ninja_jwt.routers.obtain import obtain_pair_router
from ninja_jwt.routers.verify import verify_router

from apps.core.exceptions import register_exception_handlers
from apps.core.health import HealthChecker

# API 版本号
API_VERSION = "1.0.0"

# ============================================================
# API v1 实例
# ============================================================
api_v1 = NinjaAPI(
    title="法律事务管理系统 API",
    version=API_VERSION,
    description="律师事务所案件、合同、客户管理系统",
    urls_namespace="api_v1",
)

# 注册全局异常处理器
register_exception_handlers(api_v1)

# 注册各模块路由（不指定顶层 tags，使用子路由的 tags）
from apps.core.api import router as config_router
from apps.organization.api import router as organization_router
from apps.client.api import router as client_router
from apps.cases.api import router as cases_router
from apps.contracts.api import router as contracts_router
from apps.automation.api import router as automation_router

api_v1.add_router("/config", config_router, tags=["系统配置"])
api_v1.add_router("/organization", organization_router)
api_v1.add_router("/client", client_router)
api_v1.add_router("/cases", cases_router)
api_v1.add_router("/contracts", contracts_router)
api_v1.add_router("/automation", automation_router)

# JWT 认证路由
api_v1.add_router("/token", router=obtain_pair_router, tags=["JWT认证"])
api_v1.add_router("/token", router=verify_router, tags=["JWT认证"])


# ============================================================
# 系统端点
# ============================================================

@api_v1.get("/", tags=["系统"])
def api_root(request):
    """API 根路径，返回基本信息"""
    return {
        "message": "法律事务管理系统 API",
        "version": API_VERSION,
        "docs": "/api/v1/docs",
    }


@api_v1.get("/health", tags=["系统"])
def health_check(request):
    """
    健康检查端点
    返回系统整体健康状态
    """
    health = HealthChecker.get_system_health(include_details=False)
    return health.to_dict()


@api_v1.get("/health/detail", tags=["系统"])
def health_check_detail(request):
    """
    详细健康检查端点
    返回包含磁盘空间等详细信息的健康状态
    """
    health = HealthChecker.get_system_health(include_details=True)
    return health.to_dict()


@api_v1.get("/health/live", tags=["系统"])
def liveness_probe(request):
    """
    存活探针 (Kubernetes liveness probe)
    仅检查应用是否运行
    """
    return HealthChecker.liveness_check()


@api_v1.get("/health/ready", tags=["系统"])
def readiness_probe(request):
    """
    就绪探针 (Kubernetes readiness probe)
    检查应用是否可以接收流量
    """
    return HealthChecker.readiness_check()


# 兼容性别名
api = api_v1
