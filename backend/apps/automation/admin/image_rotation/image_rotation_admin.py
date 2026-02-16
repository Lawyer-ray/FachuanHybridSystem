"""
图片自动旋转工具 Admin
提供在 Admin 后台使用图片自动旋转功能
"""

import logging
from typing import Any

from django.contrib import admin
from django.template.response import TemplateResponse

from apps.automation.models import ImageRotation

logger = logging.getLogger("apps.automation")


@admin.register(ImageRotation)
class ImageRotationAdmin(admin.ModelAdmin):
    """
    图片自动旋转工具 Admin

    使用 ImageRotation 作为占位模型
    提供图片自动旋转功能的入口
    """

    def changelist_view(self, request, extra_context=None) -> None:
        """
        自定义列表页 - 显示图片自动旋转工具页面

        Admin 层只负责:
        1. 渲染工具页面
        2. 提供 API 端点供前端调用
        """
        context = {
            "title": "图片自动旋转",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }

        return TemplateResponse(
            request,
            "admin/automation/image_rotation.html",
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
