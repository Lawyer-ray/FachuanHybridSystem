"""
Django Admin 界面自定义

集中管理 Admin 侧边栏排序、虚拟菜单、Hub 页、工具收藏等功能。
从 urls.py 提取而来，职责单一。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import URLPattern, URLResolver, path, reverse
from django.utils.translation import gettext_lazy as _

from apps.organization.views import AuthLoginView

logger = logging.getLogger(__name__)

# ============================================================
# Admin 站点标题
# ============================================================

admin.site.site_header = _(getattr(settings, "ADMIN_SITE_HEADER", "法穿AI Copilot"))
admin.site.site_title = _(getattr(settings, "ADMIN_SITE_TITLE", "法穿AI Copilot"))
admin.site.index_title = _(getattr(settings, "ADMIN_INDEX_TITLE", "欢迎来到法穿AI Copilot"))

# 覆盖 admin login 视图，注入注册上下文
_admin_login_view = AuthLoginView.as_view()


def _admin_login(request: HttpRequest, **kwargs: object) -> HttpResponse:
    return _admin_login_view(request, **kwargs)


admin.site.login = _admin_login

# ============================================================
# 侧边栏配置常量
# ============================================================

# 侧边栏 app 顺序（按以下顺序显示）
_APP_ORDER = [
    "case_handling",  # 0. 办案（虚拟菜单，聚合当事人/合同/案件）
    "reminders",  # 4. 重要日期提醒
    "automation",  # 6. 自动化工具（已收纳到其他工具）
    "other_tools",  # 7. 其他工具
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
    ],
}

# 需要在侧边栏隐藏的 app（保留直链 URL 访问）
_HIDDEN_APP_LABELS = {
    "client",  # 已收纳到「办案」
    "contracts",  # 已收纳到「办案」
    "cases",  # 已收纳到「办案」
    "contacts",  # 已收纳到「其他工具」
    "automation",
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
    "doc_converter",
    "wechat_mp",
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
    "workbench",
}

# "其他工具"聚合页应用列表
_OTHER_TOOLS_APPS = [
    {"app_label": "contacts", "name": _("案件工作人员"), "url": "/admin/contacts/"},
    {"app_label": "automation", "name": _("自动化工具"), "url": "/admin/automation/"},
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
    {"app_label": "doc_converter", "name": _("DOC 转 DOCX"), "url": "/admin/doc_converter/"},
    {"app_label": "wechat_mp", "name": _("公众号发布"), "url": "/admin/wechat_mp/"},
    {"app_label": "batch_printing", "name": _("批量打印"), "url": "/admin/batch_printing/"},
    {"app_label": "evidence_sorting", "name": _("证据整理"), "url": "/admin/evidence_sorting/"},
    {"app_label": "legal_research", "name": _("法律检索"), "url": "/admin/legal_research/"},
    {"app_label": "legal_solution", "name": _("法律方案"), "url": "/admin/legal_solution/"},
    {"app_label": "evidence", "name": _("证据管理"), "url": "/admin/evidence/"},
    {"app_label": "preservation_date", "name": _("保全日期识别"), "url": "/admin/preservation_date/"},
    {
        "app_label": "finance",
        "name": _("利息/违约金计算"),
        "url": "/admin/finance/",
        "children": [
            {"name": _("LPR利率"), "url": "/admin/finance/lprrate/"},
            {"name": _("LPR计算器"), "url": "/admin/finance/calculator/"},
        ],
    },
    {"app_label": "django_q", "name": _("任务队列"), "url": "/admin/django_q/"},
    {"app_label": "organization", "name": _("组织管理"), "url": "/admin/organization/"},
    {"app_label": "auth", "name": _("用户与权限"), "url": "/admin/auth/"},
    {"app_label": "core", "name": _("核心系统"), "url": "/admin/core/"},
    {"app_label": "reminders", "name": _("重要日期提醒"), "url": "/admin/reminders/"},
    {"app_label": "message_hub", "name": _("信息中转站"), "url": "/admin/message_hub/"},
    {"app_label": "workbench", "name": _("工作台"), "url": "/admin/workbench/"},
]

# 新用户默认收藏的子工具 URL（首次访问「其他工具」页时自动创建）
_DEFAULT_FAV_URLS = [
    "/admin/finance/calculator/",
    "/admin/express_query/expressquerytool/",
    "/admin/automation/courtsms/",
    "/admin/doc_convert/docconverttool/",
]

# "办案"聚合页应用列表
_CASE_HANDLING_APPS = [
    {"app_label": "client", "name": _("当事人管理"), "url": "/admin/client/"},
    {"app_label": "contracts", "name": _("合同管理"), "url": "/admin/contracts/"},
    {"app_label": "cases", "name": _("案件管理"), "url": "/admin/cases/"},
]


# ============================================================
# 侧边栏排序 monkey-patch
# ============================================================

_original_get_app_list = admin.site.__class__.get_app_list


def _sorted_get_app_list(self: admin.AdminSite, request: HttpRequest, app_label: str | None = None) -> list:
    # 一次性获取完整 app 列表并缓存，避免构建虚拟菜单时递归调用
    if app_label is None:
        full_app_list = _original_get_app_list(self, request, None)
        app_map = {a.get("app_label"): a for a in full_app_list}
    else:
        full_app_list = _original_get_app_list(self, request, app_label)
        app_map = {}

    app_list = full_app_list

    # 统一隐藏指定 app（仅隐藏首页/侧边栏菜单，不影响 /admin/<app_label>/ 直链）
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

    # 注入虚拟「办案」顶级菜单（侧边栏仅显示3个核心入口，Hub 页展示全部子入口）
    if app_label is None and not any(a.get("app_label") == "case_handling" for a in app_list):
        case_handling_models: list[dict[str, Any]] = []
        sidebar_labels = {
            "当事人": "/admin/client/client/",
            "合同": "/admin/contracts/contract/",
            "案件": "/admin/cases/case/",
        }
        for label, url in sidebar_labels.items():
            case_handling_models.append(
                {
                    "name": label,
                    "object_name": f"Virtual_{url.strip('/').replace('/', '_')}",
                    "perms": {"add": False, "change": False, "delete": False, "view": True},
                    "admin_url": url,
                    "add_url": None,
                    "view_only": True,
                }
            )
        app_list.append(
            {
                "app_label": "case_handling",
                "app_url": "/admin/case-handling/",
                "name": _("办案"),
                "has_perms": True,
                "models": case_handling_models,
            }
        )

    # 注入虚拟「其他工具」顶级菜单（主菜单链接 hub 页，子菜单直达各子工具）
    if app_label is None and not any(a.get("app_label") == "other_tools" for a in app_list):
        virtual_models: list[dict[str, Any]] = []
        for item in _OTHER_TOOLS_APPS:
            item_label = str(item.get("app_label", ""))
            manual_children = item.get("children")

            if manual_children:
                # 手动指定的子工具
                for child in manual_children:
                    child_url = str(child.get("url", ""))
                    child_name = str(child.get("name", ""))
                    if child_url and child_name:
                        virtual_models.append(
                            {
                                "name": child_name,
                                "object_name": f"Virtual_{child_url.strip('/').replace('/', '_')}",
                                "perms": {"add": False, "change": False, "delete": False, "view": True},
                                "admin_url": child_url,
                                "add_url": None,
                                "view_only": True,
                            }
                        )
            elif item_label:
                # 通过 app_label 自动发现子模型（从缓存的 app_map 查找，避免递归调用）
                item_app = app_map.get(item_label)
                if item_app:
                    for model in item_app.get("models", []):
                        m_name = str(model.get("name", "")).strip()
                        m_url = str(model.get("admin_url") or "").strip()
                        if m_name and m_url:
                            virtual_models.append(
                                {
                                    "name": m_name,
                                    "object_name": f"Virtual_{m_url.strip('/').replace('/', '_')}",
                                    "perms": {"add": False, "change": False, "delete": False, "view": True},
                                    "admin_url": m_url,
                                    "add_url": None,
                                    "view_only": True,
                                }
                            )

        app_list.append(
            {
                "app_label": "other_tools",
                "app_url": "/admin/automation/other-tools/",
                "name": _("其他工具"),
                "has_perms": True,
                "models": virtual_models,
            }
        )

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


# ============================================================
# Admin Hub 视图
# ============================================================


def lpr_calculator_view(request: HttpRequest) -> HttpResponse:
    """LPR利息计算器独立视图."""
    from apps.finance.models.lpr_rate import LPRRate
    from apps.finance.services.lpr.rate_service import LPRRateService

    rate_service = LPRRateService()

    try:
        latest_rate = rate_service.get_latest_rate()
    except Exception:
        latest_rate = None

    # 获取最新的几条利率记录用于参考
    recent_rates = LPRRate.objects.all()[:10]

    context: dict[str, Any] = {
        **admin.site.each_context(request),
        "title": _("利息/违约金计算器"),
        "recent_rates": recent_rates,
        "latest_rate": latest_rate,
        "is_data_current": rate_service.is_data_current(),
        "sync_url": "/admin/finance/lprrate/sync/",
    }
    return render(request, "admin/finance/lpr/calculator.html", context)


def case_handling_hub_view(request: HttpRequest) -> TemplateResponse:
    """办案聚合页。"""
    sections: list[dict[str, Any]] = []

    for item in _CASE_HANDLING_APPS:
        app_label = str(item.get("app_label", ""))
        app_url = str(item.get("url", ""))
        app_name = item.get("name", app_label)
        model_links: list[dict[str, str]] = []

        # 使用原始 get_app_list 避免触发排序和虚拟菜单构建
        app_entries = _original_get_app_list(admin.site, request, app_label)
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
        "title": _("办案"),
        "sections": sections,
    }
    return TemplateResponse(request, "admin/core/case_handling_hub.html", context)


def other_tools_hub_view(request: HttpRequest) -> TemplateResponse:
    """其他工具聚合页。"""
    from apps.core.models import ToolFavorite

    sections: list[dict[str, Any]] = []

    for item in _OTHER_TOOLS_APPS:
        app_label = str(item.get("app_label", ""))
        app_url = str(item.get("url", ""))
        app_name = item.get("name", app_label)
        model_links: list[dict[str, str]] = []

        # 支持手动指定 children（不走 app_label 自动发现）
        manual_children = item.get("children")
        if manual_children:
            model_links = [dict(c) for c in manual_children]  # type: ignore[arg-type]
        else:
            # 使用原始 get_app_list 避免触发排序和虚拟菜单构建
            app_entries = _original_get_app_list(admin.site, request, app_label)
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

    # 获取当前用户的收藏 URL 集合；首次访问时创建默认收藏
    existing_favs = ToolFavorite.objects.filter(user=request.user)
    if not existing_favs.exists():
        for url in _DEFAULT_FAV_URLS:
            ToolFavorite.objects.get_or_create(
                user=request.user,
                tool_url=url,
                defaults={"tool_name": url.strip("/").split("/")[-1].replace("_", " ").title()},
            )
        existing_favs = ToolFavorite.objects.filter(user=request.user)

    fav_urls: set[str] = set(existing_favs.values_list("tool_url", flat=True))

    context: dict[str, Any] = {
        **admin.site.each_context(request),
        "title": _("其他工具"),
        "sections": sections,
        "fav_urls": fav_urls,
    }
    return TemplateResponse(request, "admin/automation/other_tools_hub.html", context)


def reminders_calendar_redirect(_: HttpRequest) -> HttpResponseRedirect:
    """提醒 app 下的日历入口，重定向到 ReminderAdmin 日历页。"""
    return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))


def tool_favorite_toggle_view(request: HttpRequest) -> HttpResponse:
    """切换工具收藏状态（POST only）。"""
    from apps.core.models import ToolFavorite

    if request.method != "POST":
        return HttpResponse(json.dumps({"error": "Method not allowed"}), status=405, content_type="application/json")

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(json.dumps({"error": "Invalid JSON"}), status=400, content_type="application/json")

    tool_url = str(data.get("url", "")).strip()
    tool_name = str(data.get("name", "")).strip()
    if not tool_url:
        return HttpResponse(json.dumps({"error": "Missing url"}), status=400, content_type="application/json")

    fav = ToolFavorite.objects.filter(user=request.user, tool_url=tool_url).first()
    if fav:
        fav.delete()
        is_fav = False
    else:
        ToolFavorite.objects.create(user=request.user, tool_url=tool_url, tool_name=tool_name)
        is_fav = True

    return HttpResponse(
        json.dumps({"is_fav": is_fav, "url": tool_url}),
        content_type="application/json",
    )


# ============================================================
# 自定义 Admin URL 注册
# ============================================================

_original_get_urls = admin.site.get_urls


def _get_urls_with_calculator() -> list[URLResolver | URLPattern]:
    urls = _original_get_urls()
    custom_urls: list[URLResolver | URLPattern] = [
        path(
            "case-handling/",
            admin.site.admin_view(case_handling_hub_view),
            name="case_handling_hub",
        ),
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
        path(
            "automation/tool-favorite/toggle/",
            admin.site.admin_view(tool_favorite_toggle_view),
            name="automation_tool_favorite_toggle",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = _get_urls_with_calculator  # type: ignore[method-assign]


def _admin_index_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Admin 首页自动重定向到提醒日历页。"""
    return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))


admin.site.index = admin.site.admin_view(_admin_index_redirect)  # type: ignore[method-assign]
