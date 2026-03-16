"""
图片自动旋转工具 Admin
提供在 Admin 后台使用图片自动旋转功能
"""

import logging
from typing import Any

from django.contrib import admin
from django.template.response import TemplateResponse

from apps.image_rotation.models import ImageRotationTool

logger = logging.getLogger("apps.image_rotation")


@admin.register(ImageRotationTool)
class ImageRotationAdmin(admin.ModelAdmin):
    """
    图片自动旋转工具 Admin

    使用 ImageRotationTool 作为占位模型
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
            "admin/image_rotation/image_rotation.html",
            context,
        )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def get_model_perms(self, request: Any) -> dict[str, bool]:
        return {"view": True}
