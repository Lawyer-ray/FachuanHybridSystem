"""
测试工具入口 Admin
提供统一的测试工具导航入口
"""

import logging
from typing import Any

from django.contrib import admin
from django.template.response import TemplateResponse

from apps.automation.models import TestToolsHub

logger = logging.getLogger("apps.automation")


@admin.register(TestToolsHub)
class TestToolsHubAdmin(admin.ModelAdmin):
    """
    测试工具入口 Admin

    使用 TestToolsHub 作为占位模型
    提供统一的测试工具导航入口
    """

    def changelist_view(self, request, extra_context=None) -> None:
        """自定义列表页 - 显示测试工具导航"""
        # 定义所有测试工具(使用 SVG 图标)
        # SVG 图标定义
        icon_document = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="14 2 14 8 20 8"/>'
            '<line x1="16" y1="13" x2="8" y2="13"/>'
            '<line x1="16" y1="17" x2="8" y2="17"/>'
            '<polyline points="10 9 9 9 8 9"/></svg>'
        )
        icon_court = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/>'
            '<path d="M12 6v6l4 2"/></svg>'
        )
        icon_calendar = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
            '<line x1="16" y1="2" x2="16" y2="6"/>'
            '<line x1="8" y1="2" x2="8" y2="6"/>'
            '<line x1="3" y1="10" x2="21" y2="10"/>'
            '<path d="M8 14h.01"/><path d="M12 14h.01"/>'
            '<path d="M16 14h.01"/><path d="M8 18h.01"/>'
            '<path d="M12 18h.01"/><path d="M16 18h.01"/></svg>'
        )
        icon_rotate = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
            '<path d="M21 3v5h-5"/></svg>'
        )

        test_tools: list[Any] = [
            {
                "name": "交费通知书识别",
                "description": "测试交费通知书 PDF 的 OCR 识别和信息提取功能",
                "url": "automation_feenoticetest_changelist",
                "icon": icon_document,
                "color": "primary",
            },
            {
                "name": "财产保全日期识别",
                "description": "从法院文书中识别财产保全措施的到期时间",
                "url": "automation_preservationdatetest_changelist",
                "icon": icon_calendar,
                "color": "warning",
            },
            {
                "name": "图片自动旋转",
                "description": "批量处理图片方向,自动识别 EXIF 信息并旋转校正,支持手动调整和 ZIP 导出",
                "url": "image_rotation_imagerotationtool_changelist",
                "icon": icon_rotate,
                "color": "info",
            },
        ]

        context = {
            "title": "测试工具",
            "test_tools": test_tools,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }

        return TemplateResponse(
            request,
            "admin/automation/test_tools_hub.html",
            context,
        )

    def has_add_permission(self, request) -> None:
        """禁用添加功能"""
        return False

    def has_delete_permission(self, request, obj=None) -> None:
        """禁用删除功能"""
        return False

    def has_change_permission(self, request, obj=None) -> None:
        """禁用修改功能"""
        return False

    def has_module_permission(self, request) -> bool:
        """隐藏在 Admin 菜单中"""
        return False
