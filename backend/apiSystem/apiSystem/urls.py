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
from django.urls import URLPattern, URLResolver, include, path, reverse
from django.utils.translation import gettext_lazy as _

from apps.organization.views import register

from .api import api_v1

# 配置 Django Admin 界面标题
admin.site.site_header = _(getattr(settings, "ADMIN_SITE_HEADER", "法穿AI案件管理系统"))
admin.site.site_title = _(getattr(settings, "ADMIN_SITE_TITLE", "法穿AI案件管理系统"))
admin.site.index_title = _(getattr(settings, "ADMIN_INDEX_TITLE", "欢迎来到法穿AI案件管理系统"))

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
    "automation": [  # 自动化工具
        "courtsms",  # 法院短信
        "preservationquote",  # 财产保全询价
        "othertoolshub",  # 其他工具
    ],
}

# 需要在侧边栏隐藏的 app（保留直链 URL 访问）
_HIDDEN_APP_LABELS = {
    "fee_notice",
    "document_recognition",
    "pdf_splitting",
    "batch_printing",
    "story_viz",
    "documents",
    "chat_records",
    "sales_dispute",
    "enterprise_data",
    "invoice_recognition",
    "contract_review",
    "image_rotation",
    "express_query",
    "doc_convert",
    "evidence_sorting",
    "legal_research",
    "legal_solution",
    "evidence",
    "preservation_date",
    "finance",
    "django_q",
    "organization",
    "auth",
    "core",
    "reminders",
    "message_hub",
}

# “其他工具”聚合页应用列表
_OTHER_TOOLS_APPS = [
    {"app_label": "fee_notice", "name": _("交费通知书识别"), "url": "/admin/fee_notice/"},
    {"app_label": "document_recognition", "name": _("文书智能识别"), "url": "/admin/document_recognition/"},
    {"app_label": "pdf_splitting", "name": _("PDF 拆解"), "url": "/admin/pdf_splitting/"},
    {"app_label": "story_viz", "name": _("故事可视化"), "url": "/admin/story_viz/"},
    {"app_label": "documents", "name": _("文书生成"), "url": "/admin/documents/"},
    {"app_label": "chat_records", "name": _("聊天记录"), "url": "/admin/chat_records/"},
    {"app_label": "sales_dispute", "name": _("销售纠纷"), "url": "/admin/sales_dispute/"},
    {"app_label": "enterprise_data", "name": _("企业数据工作台"), "url": "/admin/enterprise_data/"},
    {"app_label": "invoice_recognition", "name": _("发票识别"), "url": "/admin/invoice_recognition/"},
    {"app_label": "contract_review", "name": _("合同审核"), "url": "/admin/contract_review/"},
    {"app_label": "image_rotation", "name": _("图片自动旋转"), "url": "/admin/image_rotation/"},
    {"app_label": "express_query", "name": _("快递查询"), "url": "/admin/express_query/"},
    {"app_label": "doc_convert", "name": _("文档转换"), "url": "/admin/doc_convert/"},
    {"app_label": "evidence_sorting", "name": _("证据整理"), "url": "/admin/evidence_sorting/"},
    {"app_label": "legal_research", "name": _("法律检索"), "url": "/admin/legal_research/"},
    {"app_label": "legal_solution", "name": _("法律方案"), "url": "/admin/legal_solution/"},
    {"app_label": "evidence", "name": _("证据管理"), "url": "/admin/evidence/"},
    {"app_label": "preservation_date", "name": _("保全日期识别"), "url": "/admin/preservation_date/"},
    {"app_label": "finance", "name": _("利息/违约金计算"), "url": "/admin/finance/"},
    {"app_label": "django_q", "name": _("任务队列"), "url": "/admin/django_q/"},
    {"app_label": "organization", "name": _("组织管理"), "url": "/admin/organization/"},
    {"app_label": "auth", "name": _("用户与权限"), "url": "/admin/auth/"},
    {"app_label": "core", "name": _("核心系统"), "url": "/admin/core/"},
    {"app_label": "reminders", "name": _("重要日期提醒"), "url": "/admin/reminders/"},
    {"app_label": "message_hub", "name": _("信息中转站"), "url": "/admin/message_hub/"},
]

_original_get_app_list = admin.site.__class__.get_app_list


def _sorted_get_app_list(self: admin.AdminSite, request: HttpRequest, app_label: str | None = None) -> list:
    app_list = _original_get_app_list(self, request, app_label)

    # 统一隐藏指定 app（仅隐藏首页/侧边栏菜单，不影响 /admin/<app_label>/ 直达）
    if app_label is None:
        app_list = [app for app in app_list if app.get("app_label") not in _HIDDEN_APP_LABELS]

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

    # 向 automation app 添加“其他工具”聚合入口
    for app in app_list:
        if app.get("app_label") == "automation":
            other_tools_model = {
                "name": _("其他工具"),
                "object_name": "OtherToolsHub",
                "perms": {"add": False, "change": False, "delete": False, "view": True},
                "admin_url": "/admin/automation/other-tools/",
                "add_url": None,
                "view_only": True,
            }
            models = app.setdefault("models", [])
            if not any(item.get("object_name") == "OtherToolsHub" for item in models):
                models.append(other_tools_model)

            model_order = _MODEL_ORDER.get("automation", [])
            if model_order:
                models.sort(
                    key=lambda m: (
                        model_order.index(str(m.get("object_name", "")).lower())
                        if str(m.get("object_name", "")).lower() in model_order
                        else 999
                    )
                )
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


def lpr_calculator_view(request: HttpRequest) -> HttpResponse:
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


def other_tools_hub_view(request: HttpRequest) -> TemplateResponse:
    """其他工具聚合页。"""
    sections: list[dict[str, Any]] = []

    for item in _OTHER_TOOLS_APPS:
        app_label = str(item.get("app_label", ""))
        app_url = str(item.get("url", ""))
        app_name = item.get("name", app_label)
        app_entries = admin.site.get_app_list(request, app_label=app_label)
        model_links: list[dict[str, str]] = []

        if app_entries:
            first_app = app_entries[0]
            app_url = str(first_app.get("app_url") or app_url)
            for model in first_app.get("models", []):
                name = str(model.get("name", "")).strip()
                url = str(model.get("admin_url") or "").strip()
                if name and url:
                    model_links.append({"name": name, "url": url})

        sections.append(
            {
                "name": app_name,
                "url": app_url,
                "children": model_links,
            }
        )

    context: dict[str, Any] = {
        **admin.site.each_context(request),
        "title": _("其他工具"),
        "sections": sections,
    }
    return TemplateResponse(request, "admin/automation/other_tools_hub.html", context)


def reminders_calendar_redirect(_: HttpRequest) -> HttpResponseRedirect:
    """提醒 app 下的日历入口，重定向到 ReminderAdmin 日历页。"""
    return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))


# 注册 LPR 计算器 URL 到 admin site
_original_get_urls = admin.site.get_urls


def _get_urls_with_calculator() -> list[URLResolver | URLPattern]:
    urls = _original_get_urls()
    custom_urls: list[URLResolver | URLPattern] = [
        path(
            "finance/calculator/",
            admin.site.admin_view(lpr_calculator_view),
            name="finance_lpr_calculator",
        ),
        path(
            "automation/other-tools/",
            admin.site.admin_view(other_tools_hub_view),
            name="automation_other_tools_hub",
        ),
        path(
            "reminders/calendar/",
            admin.site.admin_view(reminders_calendar_redirect),
            name="reminders_calendar_entry",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = _get_urls_with_calculator  # type: ignore[method-assign]


def _admin_index_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Admin 首页自动重定向到提醒日历页。"""
    return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))


admin.site.index = admin.site.admin_view(_admin_index_redirect)  # type: ignore[method-assign]


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
