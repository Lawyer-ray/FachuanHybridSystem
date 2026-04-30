"""
API 主入口
统一注册所有路由和异常处理
支持 API 版本控制
"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import NinjaAPI
from ninja.renderers import BaseRenderer

# 兼容 django-ninja 1.6 Router API 变更（ninja-extra 仍访问 Router.api）
from ninja_extra.router import Router as NinjaExtraRouter

if not hasattr(NinjaExtraRouter, "api"):
    NinjaExtraRouter.api = None  # type: ignore[attr-defined]

from ninja_jwt.routers.obtain import obtain_pair_router
from ninja_jwt.routers.verify import verify_router

from apps.core.exceptions import register_exception_handlers
from apps.core.infrastructure import (
    HealthChecker,
    ResourceUsage,
    get_resource_status,
    get_resource_usage,
    resource_monitor,
)
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.admin_access import ensure_admin_request
from apps.core.security.auth import JWTOrSessionAuth

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
# OpenAPI tags 定义（按业务模块排序，含中文描述）
_OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "系统", "description": "系统信息与健康检查"},
    {"name": "资源监控", "description": "服务器资源使用与监控"},
    {"name": "JWT认证", "description": "JWT 令牌获取与验证"},
    {"name": "认证登录", "description": "用户登录、登出与信息"},
    {"name": "律师管理", "description": "律师信息管理"},
    {"name": "账号凭证", "description": "外部系统账号凭证"},
    {"name": "律所管理", "description": "律师事务所管理"},
    {"name": "团队管理", "description": "律师团队管理"},
    {"name": "客户管理", "description": "客户信息的增删改查"},
    {"name": "客户证件", "description": "客户身份证件管理"},
    {"name": "财产线索", "description": "客户财产线索管理"},
    {"name": "客户导入", "description": "批量导入客户数据"},
    {"name": "案件管理", "description": "案件信息管理"},
    {"name": "案件当事人", "description": "案件当事人管理"},
    {"name": "案件指派", "description": "案件律师指派"},
    {"name": "案件日志", "description": "案件日志记录"},
    {"name": "案件授权", "description": "案件访问授权"},
    {"name": "案件案号", "description": "案件案号管理"},
    {"name": "案由主管机关", "description": "案由与主管机关查询"},
    {"name": "诉讼费计算", "description": "诉讼费用计算器"},
    {"name": "案件文件夹生成", "description": "案件文件夹自动生成"},
    {"name": "案件文件夹绑定", "description": "案件文件夹绑定"},
    {"name": "案件材料", "description": "案件材料管理"},
    {"name": "案件文件夹自动捕获", "description": "案件文件夹自动捕获"},
    {"name": "案件导入", "description": "批量导入案件数据"},
    {"name": "合同管理", "description": "合同信息管理"},
    {"name": "合同收款", "description": "合同收款记录"},
    {"name": "财务统计", "description": "合同财务统计"},
    {"name": "补充协议", "description": "合同补充协议"},
    {"name": "文件夹绑定", "description": "合同文件夹绑定"},
    {"name": "文件夹自动捕获", "description": "合同文件夹自动捕获"},
    {"name": "合同审查", "description": "AI 合同审查"},
    {"name": "文件模板", "description": "文档模板管理"},
    {"name": "文件夹模板", "description": "文件夹模板管理"},
    {"name": "替换词", "description": "文档占位符/替换词管理"},
    {"name": "文档生成", "description": "基于模板生成文档"},
    {"name": "诉讼文书生成", "description": "AI 辅助诉讼文书生成"},
    {"name": "授权委托材料生成", "description": "授权委托书材料生成"},
    {"name": "财产保全材料生成", "description": "财产保全材料生成"},
    {"name": "案件模板下载", "description": "案件模板文件下载"},
    {"name": "外部模板", "description": "外部文档模板管理"},
    {"name": "证据管理", "description": "证据材料管理"},
    {"name": "案件材料整理", "description": "案件证据材料分类整理"},
    {"name": "模拟庭审", "description": "AI 模拟庭审"},
    {"name": "案例检索", "description": "法律案例检索"},
    {"name": "梳理聊天记录", "description": "聊天记录梳理与导出"},
    {"name": "买卖纠纷计算", "description": "买卖合同纠纷利息计算"},
    {"name": "LPR利率", "description": "LPR 利率查询"},
    {"name": "法院短信处理", "description": "法院短信解析与处理"},
    {"name": "文书送达自动下载", "description": "法院文书自动下载"},
    {"name": "财产保全询价", "description": "财产保全询价查询"},
    {"name": "财产保全日期识别", "description": "财产保全日期 AI 识别"},
    {"name": "一张网立案", "description": "一张网在线立案"},
    {"name": "一张网担保", "description": "一张网担保信息查询"},
    {"name": "OA立案", "description": "OA 系统自动立案"},
    {"name": "要素式转换", "description": "传统文书转要素式文书"},
    {"name": "LLM 服务", "description": "大语言模型服务接口"},
    {"name": "国际化", "description": "多语言支持"},
    {"name": "性能监控", "description": "自动化性能监控"},
    {"name": "文档处理", "description": "文档内容提取与处理"},
    {"name": "自动命名", "description": "AI 自动文件命名"},
    {"name": "AI工具", "description": "AI 集成工具接口"},
    {"name": "验证码识别", "description": "验证码 AI 识别"},
    {"name": "图片旋转", "description": "图片旋转校正"},
    {"name": "发票识别", "description": "发票 OCR 识别"},
    {"name": "交费通知书识别", "description": "法院交费通知书识别"},
    {"name": "法院文书识别", "description": "法院文书 AI 识别"},
    {"name": "PDF 拆解", "description": "PDF 文件拆分"},
    {"name": "批量打印", "description": "批量打印管理"},
    {"name": "故事可视化", "description": "案件故事可视化"},
    {"name": "企业数据查询", "description": "企业工商信息查询"},
    {"name": "重要日期提醒", "description": "案件重要日期提醒"},
    {"name": "收件箱", "description": "消息收件箱"},
]

api_v1 = NinjaAPI(
    title="法穿AI Copilot API",
    version=API_VERSION,
    description="律师事务所案件、合同、客户管理系统",
    urls_namespace="api_v1",
    renderer=UTF8JSONRenderer(),
    servers=[{"url": "/", "description": "当前服务器"}],
    openapi_extra={"tags": _OPENAPI_TAGS},
)

# 注册全局异常处理器
register_exception_handlers(api_v1)


# ============================================================
# 注册应用路由
# ============================================================


def _register_app_routers() -> None:
    from apps.automation.api import router as automation_router
    from apps.automation.api.court_filing_api import router as court_filing_router
    from apps.automation.api.court_guarantee_api import router as court_guarantee_router
    from apps.cases.api import router as cases_router
    from apps.chat_records.api import router as chat_records_router
    from apps.client.api import router as client_router
    from apps.contract_review.api.review_api import router as contract_review_router
    from apps.contracts.api import router as contracts_router
    from apps.core.api import router as config_router
    from apps.core.api.i18n_api import i18n_router
    from apps.core.api.ninja_llm_api import llm_router
    from apps.document_recognition.api import router as document_recognition_router
    from apps.documents.api import (
        authorization_material_router,
        case_template_download_router,
        document_router,
        external_template_router,
        folder_template_router,
        generation_router,
        litigation_generation_router,
        placeholder_router,
        preservation_materials_router,
    )
    from apps.enterprise_data.api import router as enterprise_data_router
    from apps.evidence.api import evidence_router
    from apps.evidence_sorting.api import router as evidence_sorting_router
    from apps.fee_notice.api import router as fee_notice_router
    from apps.litigation_ai.api.litigation_api import router as litigation_router
    from apps.litigation_ai.api.mock_trial_api import router as mock_trial_router
    from apps.image_rotation.api import router as image_rotation_router
    from apps.invoice_recognition.api import router as invoice_recognition_router
    from apps.legal_research.api import router as legal_research_router
    from apps.message_hub.api import router as inbox_router
    from apps.organization.api import router as organization_router
    from apps.pdf_splitting.api import router as pdf_splitting_router
    from apps.batch_printing.api import router as batch_printing_router
    from apps.preservation_date.api import router as preservation_date_router
    from apps.reminders.api import router as reminders_router
    from apps.story_viz.api import router as story_viz_router

    api_v1.add_router("/config", config_router)
    api_v1.add_router("/llm", llm_router)
    api_v1.add_router("/i18n", i18n_router)
    api_v1.add_router("/organization", organization_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/client", client_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/cases", cases_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/contracts", contracts_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/automation", automation_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/image-rotation", image_rotation_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/invoice-recognition", invoice_recognition_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/fee-notice", fee_notice_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/preservation-date", preservation_date_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/document-recognition", document_recognition_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/pdf-splitting", pdf_splitting_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/batch-printing", batch_printing_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/story-viz", story_viz_router, auth=JWTOrSessionAuth())
    api_v1.add_router("/enterprise-data", enterprise_data_router, auth=JWTOrSessionAuth(), tags=["企业数据查询"])
    api_v1.add_router("/reminders", reminders_router)
    api_v1.add_router("/inbox", inbox_router)
    api_v1.add_router("/chat-records", chat_records_router, tags=["梳理聊天记录"])

    api_v1.add_router("/documents", document_router, tags=["文件模板"])
    api_v1.add_router("/documents", folder_template_router, tags=["文件夹模板"])
    api_v1.add_router("/documents", placeholder_router, tags=["替换词"])
    api_v1.add_router("/documents", generation_router, tags=["文档生成"])
    api_v1.add_router("/documents", litigation_generation_router, tags=["诉讼文书生成"])
    api_v1.add_router("/documents", authorization_material_router, tags=["授权委托材料生成"])
    api_v1.add_router("/documents", preservation_materials_router, tags=["财产保全材料生成"])
    api_v1.add_router("/documents", case_template_download_router, tags=["案件模板下载"])
    api_v1.add_router("/documents/external-templates", external_template_router, tags=["外部模板"])
    api_v1.add_router("/evidence", evidence_router, tags=["证据管理"])
    api_v1.add_router("/evidence-sorting", evidence_sorting_router, tags=["案件材料整理"])
    api_v1.add_router("/litigation", litigation_router, auth=JWTOrSessionAuth(), tags=["诉讼文书生成"])
    api_v1.add_router("/mock-trial", mock_trial_router, auth=JWTOrSessionAuth(), tags=["模拟庭审"])
    api_v1.add_router("/contract-review", contract_review_router, auth=JWTOrSessionAuth(), tags=["合同审查"])
    api_v1.add_router("/legal-research", legal_research_router, auth=JWTOrSessionAuth(), tags=["案例检索"])

    from apps.oa_filing.api.filing_api import router as oa_filing_router

    api_v1.add_router("/oa-filing", oa_filing_router, auth=JWTOrSessionAuth(), tags=["OA立案"])

    from apps.doc_convert.api import router as doc_convert_router

    api_v1.add_router("/doc-convert", doc_convert_router, auth=JWTOrSessionAuth(), tags=["要素式转换"])

    from apps.oa_filing.api.client_import_api import router as client_import_router

    # client_import_router 内部路径已包含 /client-import，前缀保持空避免变成 /client-import/client-import
    api_v1.add_router("", client_import_router, auth=JWTOrSessionAuth(), tags=["客户导入"])

    from apps.oa_filing.api.case_import_api import router as case_import_router

    # case_import_router 内部路径已包含 /case-import，前缀保持空避免变成 /case-import/case-import
    api_v1.add_router("", case_import_router, auth=JWTOrSessionAuth(), tags=["案件导入"])

    from apps.sales_dispute.api import router as sales_dispute_router

    api_v1.add_router("/sales-dispute", sales_dispute_router, tags=["买卖纠纷计算"])

    # LPR金融工具
    from apps.finance.api.lpr_api import router as lpr_router

    api_v1.add_router("/lpr", lpr_router, auth=JWTOrSessionAuth(), tags=["LPR利率"])

    api_v1.add_router("/court-filing", court_filing_router, auth=JWTOrSessionAuth(), tags=["一张网立案"])
    api_v1.add_router("/court-guarantee", court_guarantee_router, auth=JWTOrSessionAuth(), tags=["一张网担保"])


# 防止 uvicorn reload 导致重复注册 - 在 api_v1 对象上设置标志
def _ensure_routers_registered() -> None:
    if getattr(api_v1, "_routers_registered", False):
        return
    api_v1._routers_registered = True  # type: ignore[attr-defined]
    _register_app_routers()


_ensure_routers_registered()

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
    return health.to_dict()


@api_v1.get("/health/detail", tags=["系统"], auth=JWTOrSessionAuth())
def health_check_detail(request: HttpRequest) -> dict[str, Any]:
    """
    详细健康检查端点
    返回包含磁盘空间等详细信息的健康状态
    """
    ensure_admin_request(request, message="无权限访问健康检查详情", code="PERMISSION_DENIED")

    health = HealthChecker.get_system_health(include_details=True)
    return health.to_dict()


@api_v1.get("/health/live", tags=["系统"])
def liveness_probe(request: HttpRequest) -> dict[str, Any]:
    """
    存活探针 (Kubernetes liveness probe)
    仅检查应用是否运行
    """
    return HealthChecker.liveness_check()


@api_v1.get("/health/ready", tags=["系统"])
def readiness_probe(request: HttpRequest) -> dict[str, Any]:
    """
    就绪探针 (Kubernetes readiness probe)
    检查应用是否可以接收流量
    """
    return HealthChecker.readiness_check()


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
    return get_resource_status()


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
