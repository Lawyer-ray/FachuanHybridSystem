"""
URL configuration for apiSystem project.

支持 API 版本控制：
- /api/v1/ - API v1 版本
- /api/ - 重定向到 /api/v1/
"""

from typing import Any

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import URLPattern, include, path, reverse
from django.utils.translation import gettext_lazy as _

from apps.organization.views import register

from .api import api_v1

# 配置 Django Admin 界面标题
admin.site.site_header = _(getattr(settings, "ADMIN_SITE_HEADER", _("法穿AI案件管理系统")))
admin.site.site_title = _(getattr(settings, "ADMIN_SITE_TITLE", _("法穿AI案件管理系统")))
admin.site.index_title = _(getattr(settings, "ADMIN_INDEX_TITLE", _("欢迎来到法穿AI案件管理系统")))

# 侧边栏 app 顺序（按以下顺序显示）
_APP_ORDER = [
    "client",  # 1. 当事人管理
    "contracts",  # 2. 合同管理
    "cases",  # 3. 案件管理
    "reminders",  # 4. 重要日期提醒
    "automation",  # 6. 自动化工具
    "fee_notice",  # 6.1 交费通知书识别
    "document_recognition",  # 6.2 文书智能识别
    "pdf_splitting",  # 6.25 PDF 拆解
    "documents",  # 7. 文书生成
    "chat_records",  # 8. 聊天记录
    "litigation_ai",  # 9. AI 诉讼文书
    "core",  # 10. 核心系统
    "django_q",  # 11. 任务队列
]

# 各 app 内模型顺序（按以下顺序显示）
_MODEL_ORDER: dict[str, list[str]] = {
    "cases": [  # 案件管理
        "case",  # 案件
        "caselog",  # 日志
        "caselogattachment",  # 日志附件
        "casechat",  # 群聊
    ],
}

_original_get_app_list = admin.site.__class__.get_app_list


def _sorted_get_app_list(self: admin.AdminSite, request: HttpRequest, app_label: str | None = None) -> list:  # type: ignore[override]
    app_list = _original_get_app_list(self, request, app_label)
    app_list.sort(key=lambda a: _APP_ORDER.index(a["app_label"]) if a["app_label"] in _APP_ORDER else 999)

    # 按 app 内模型顺序排序
    for app in app_list:
        app_label_str = app.get("app_label", "")
        if app_label_str in _MODEL_ORDER and "models" in app:
            model_order = _MODEL_ORDER[app_label_str]
            app["models"].sort(
                key=lambda m: (
                    model_order.index(m["object_name"].lower()) if m["object_name"].lower() in model_order else 999
                )
            )

    # 向 finance app 添加 LPR 计算器链接
    for app in app_list:
        if app.get("app_label") == "finance":
            # 添加计算器作为虚拟模型项
            calculator_model = {
                "name": _("利息/违约金计算器"),
                "object_name": "LPRCalculator",
                "perms": {"add": False, "change": False, "delete": False, "view": True},
                "admin_url": "/admin/finance/calculator/",
                "add_url": None,
                "view_only": True,
            }
            # 插入到 models 列表开头
            if "models" in app:
                app["models"].insert(0, calculator_model)
            else:
                app["models"] = [calculator_model]
            break

    # 向 reminders app 添加日历链接
    for app in app_list:
        if app.get("app_label") == "reminders":
            calendar_model = {
                "name": _("提醒日历"),
                "object_name": "ReminderCalendar",
                "perms": {"add": False, "change": False, "delete": False, "view": True},
                "admin_url": "/admin/reminders/calendar/",
                "add_url": None,
                "view_only": True,
            }
            if "models" in app:
                app["models"].insert(0, calendar_model)
            else:
                app["models"] = [calendar_model]
            break

    return app_list


admin.site.__class__.get_app_list = _sorted_get_app_list  # type: ignore[method-assign]


def lpr_calculator_view(request: HttpRequest) -> TemplateResponse:
    """LPR利息计算器独立视图."""
    from apps.finance.models.lpr_rate import LPRRate

    # 获取最新的几条利率记录用于参考
    recent_rates = LPRRate.objects.all()[:10]

    context: dict[str, Any] = {
        **admin.site.each_context(request),
        "title": _("利息/违约金计算器"),
        "recent_rates": recent_rates,
    }
    return render(request, "admin/finance/lpr/calculator.html", context)


def reminders_calendar_redirect(_: HttpRequest) -> HttpResponseRedirect:
    """提醒 app 下的日历入口，重定向到 ReminderAdmin 日历页。"""
    return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))


# 注册 LPR 计算器 URL 到 admin site
_original_get_urls = admin.site.get_urls


def _get_urls_with_calculator() -> list[URLPattern]:
    urls = _original_get_urls()
    custom_urls: list[URLPattern] = [
        path(
            "finance/calculator/",
            admin.site.admin_view(lpr_calculator_view),
            name="finance_lpr_calculator",
        ),
        path(
            "reminders/calendar/",
            admin.site.admin_view(reminders_calendar_redirect),
            name="reminders_calendar_entry",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = _get_urls_with_calculator  # type: ignore[method-assign]


def index_view(request: HttpRequest) -> HttpResponse:
    """首页视图"""
    return render(request, "index.html")


def root_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """根路径重定向到首页"""
    return HttpResponseRedirect("/index/")


def api_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """将 /api/ 重定向到 /api/v1/"""
    new_path = request.path.replace("/api/", "/api/v1/", 1)
    if request.META.get("QUERY_STRING"):
        new_path += "?" + request.META["QUERY_STRING"]
    return HttpResponseRedirect(new_path)


def favicon_view(request: HttpRequest) -> HttpResponse:
    """返回空的favicon响应，避免404错误"""
    return HttpResponse(status=204)  # No Content


def chrome_devtools_probe_view(request: HttpRequest) -> HttpResponse:
    """返回空响应，避免 Chrome DevTools 探测请求产生 404 日志。"""
    return HttpResponse(status=204)  # No Content


def health_view(request: HttpRequest) -> HttpResponse:
    """健康检查端点，用于 liveness probe"""
    from django.db import connection

    try:
        connection.ensure_connection()
        return HttpResponse("ok")
    except Exception:
        return HttpResponse("db unavailable", status=503)


urlpatterns = [
    path("admin/register/", register, name="admin_register"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", api_v1.urls),
    path("api/", api_redirect),
    path("favicon.ico", favicon_view, name="favicon"),
    path(".well-known/appspecific/com.chrome.devtools.json", chrome_devtools_probe_view, name="chrome_devtools_probe"),
    path("health/", health_view, name="health"),
    path("index/", index_view, name="index"),
    # 根路径重定向到首页 - 必须在最后
    path("", root_redirect),
]

# 媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
