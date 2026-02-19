"""
自动化工具二级菜单配置
通过自定义 app_list 实现分组显示和侧边栏排序

自动化工具栏目：文书送达定时任务、法院短信、财产保全询价、测试法院系统、文书智能识别
自动化记录栏目：Token管理、Token获取历史、文书查询历史、法院文书、任务管理

侧边栏顺序：
1. Client CRM（当事人管理）
2. Contracts（合同管理）
3. CASES（案件管理）
4. 自动化工具
5. 自动化记录
6. 核心系统
7. ORGANIZATION（组织管理）
8. DJANGO Q
9. 认证和授权
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

# 侧边栏排序配置
APP_ORDER = [
    "client",  # 1. Client CRM（当事人管理）
    "contracts",  # 2. Contracts（合同管理）
    "cases",  # 3. CASES（案件管理）
    "automation",  # 4. 自动化工具
    "automation_records",  # 5. 自动化记录（虚拟分组）
    "core",  # 6. 核心系统
    "organization",  # 7. ORGANIZATION（组织管理）
    "django_q",  # 8. DJANGO Q
    "auth",  # 9. 认证和授权
]


def _is_tool_model(model: dict[str, Any]) -> bool:
    """判断是否为自动化工具模型"""
    model_name = model.get("object_name", "")
    model_verbose_name = model.get("name", "")
    tool_names = {
        "DocumentDeliverySchedule", "CourtSMS", "PreservationQuote",
        "InsuranceQuote", "TestCourt", "DocumentRecognitionProxy",
    }
    tool_verbose = {"文书送达定时任务", "法院短信", "财产保全询价", "测试法院", "文书智能识别"}
    return (
        any(n in model_name for n in tool_names)
        or any(v in model_verbose_name for v in tool_verbose)
    )


def _is_record_model(model: dict[str, Any]) -> bool:
    """判断是否为自动化记录模型"""
    model_name = model.get("object_name", "")
    model_verbose_name = model.get("name", "")
    record_names = {"CourtToken", "TokenAcquisitionHistory", "DocumentQueryHistory", "CourtDocument", "ScraperTask"}
    record_verbose = {"Token管理", "Token获取历史", "文书查询历史", "法院文书", "任务管理", "爬虫任务"}
    return (
        any(n in model_name for n in record_names)
        or any(v in model_verbose_name for v in record_verbose)
    )


def _split_automation_models(automation_app: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    """将 automation 模型分为工具和记录两组"""
    tool_models = []
    record_models = []
    for model in automation_app.get("models", []):
        if _is_tool_model(model):
            tool_models.append(model)
        elif _is_record_model(model):
            record_models.append(model)
    return tool_models, record_models


def _rebuild_app_list(
    app_list: list[Any], automation_app: dict[str, Any], automation_index: int
) -> list[Any]:
    """重建包含分组的 app_list"""
    tool_models, record_models = _split_automation_models(automation_app)

    if not record_models and not tool_models:
        app_list.pop(automation_index)
        return app_list

    if record_models:
        record_group: dict[str, Any] = {
            "name": "自动化记录",
            "app_label": "automation_records",
            "app_url": "/admin/automation/",
            "has_module_perms": True,
            "models": record_models,
        }
        if tool_models:
            automation_app["models"] = tool_models
            app_list.insert(automation_index + 1, record_group)
        else:
            app_list[automation_index] = record_group
    else:
        automation_app["models"] = tool_models

    return app_list


def customize_admin_index(admin_site: Any) -> None:
    """
    自定义 admin 首页：
    1. 将 automation 模型分为两个分组（自动化工具、自动化记录）
    2. 按指定顺序排列侧边栏
    """
    original_app_list = admin_site.get_app_list

    def custom_app_list(request: Any, app_label: Any = None) -> Any:
        app_list = original_app_list(request, app_label)

        automation_app = None
        automation_index = None
        for idx, app in enumerate(app_list):
            if app.get("app_label") == "automation":
                automation_app = app
                automation_index = idx
                break

        if automation_app is not None and automation_index is not None:
            app_list = _rebuild_app_list(app_list, automation_app, automation_index)

        def get_app_order(app: dict[str, Any]) -> int:
            try:
                return APP_ORDER.index(app.get("app_label", ""))
            except ValueError:
                return len(APP_ORDER)

        app_list.sort(key=get_app_order)
        return app_list

    admin_site.get_app_list = custom_app_list
