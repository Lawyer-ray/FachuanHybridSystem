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
class TestToolsHubAdmin(admin.ModelAdmin):  # pragma: no cover
    """
    测试工具入口 Admin

    使用 TestToolsHub 作为占位模型
    提供统一的测试工具导航入口
    """

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:  # pragma: no cover
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
        icon_rotate = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
            '<path d="M21 3v5h-5"/></svg>'
        )
        icon_history = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 3v5h5"/>'
            '<path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/>'
            '<path d="M12 7v5l4 2"/></svg>'
        )

        test_tools: list[Any] = [
            {
                "name": "图片自动旋转",
                "description": "批量处理图片方向,自动识别 EXIF 信息并旋转校正,支持手动调整和 ZIP 导出",
                "url": "image_rotation_imagerotationtool_changelist",
                "icon": icon_rotate,
                "color": "info",
                "cta": "进入测试",
            },
            # 文档快照：合同/案件文件每次被**覆盖之前**的旧内容都在这里。
            # 从主菜单收进「其他工具」的理由：它不是日常操作入口，是「改坏了来这一版」的
            # 兜底页——放在主菜单里只会增加噪声，但必须**找得到**，否则等于没有版本历史。
            {
                "name": "文档快照",
                "description": (
                    "合同/案件文件每次被覆盖前自动存一份完整旧内容"
                    "（编辑器保存、AI 直改、审查落笔、回滚各一种原因），"
                    "可回滚到任意一版；快照只追加，不可编辑也不可删"
                ),
                "url": "doc_workspace_docsnapshot_changelist",
                "icon": icon_history,
                "color": "secondary",
                "cta": "查看版本历史",
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

    def has_add_permission(self, request: Any) -> bool:  # pragma: no cover
        """禁用添加功能"""
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:  # pragma: no cover
        """禁用删除功能"""
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:  # pragma: no cover
        """禁用修改功能"""
        return False

    def has_module_permission(self, request: Any) -> bool:  # pragma: no cover
        """隐藏在 Admin 菜单中"""
        return False
