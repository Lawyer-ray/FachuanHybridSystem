"""
交费通知书识别测试 Admin
提供在 Admin 后台测试交费通知书识别功能
"""

import logging
from typing import Any

from django.contrib import admin
from django.template.response import TemplateResponse

from apps.automation.models import FeeNoticeTest

logger = logging.getLogger("apps.automation")


@admin.register(FeeNoticeTest)
class FeeNoticeTestAdmin(admin.ModelAdmin):
    """
    交费通知书识别测试 Admin

    使用 FeeNoticeTest 作为占位模型
    提供交费通知书识别测试功能的入口
    """

    def changelist_view(self, request, extra_context=None) -> None:
        """
        自定义列表页 - 显示交费通知书识别测试页面

        Admin 层只负责:
        1. 渲染测试页面
        2. 提供 API 端点供前端调用
        """
        context = {
            "title": "交费通知书识别测试",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }

        return TemplateResponse(
            request,
            "admin/automation/fee_notice_test.html",
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
