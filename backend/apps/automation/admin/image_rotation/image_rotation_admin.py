"""
图片自动旋转工具 Admin
提供在 Admin 后台使用图片自动旋转功能
"""

import logging
from typing import Any

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.automation.models import ImageRotation

logger = logging.getLogger("apps.automation")


@admin.register(ImageRotation)
class ImageRotationAdmin(admin.ModelAdmin):
    """
    图片自动旋转工具 Admin

    使用 ImageRotation 作为占位模型
    提供图片自动旋转功能的入口
    """

    def changelist_view(self, request, extra_context=None) -> HttpResponseRedirect:
        """兼容旧 URL，重定向到独立 app 的新入口。"""
        return HttpResponseRedirect(
            reverse("admin:image_rotation_imagerotationtool_changelist"),
        )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def get_model_perms(self, request: Any) -> dict[str, bool]:
        # Hide legacy entry from admin index but keep URL-compatible redirect.
        return {}
