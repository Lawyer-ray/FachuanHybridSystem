"""
法院短信处理 Django Admin 界面

提供短信记录管理、状态查看、手动处理等功能。
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.urls import path

from apps.automation.models import CourtSMS

from .court_sms_admin_actions import CourtSMSAdminActions
from .court_sms_admin_base import CourtSMSAdminBase


@admin.register(CourtSMS)
class CourtSMSAdmin(CourtSMSAdminActions, CourtSMSAdminBase):
    """法院短信管理（组合 Base + Actions）"""

    ordering = ("-received_at",)
    actions = ["retry_processing_action"]

    def get_urls(self) -> list[Any]:
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls: list[Any] = [
            path(
                "submit/",
                self.admin_site.admin_view(self.submit_sms_view),
                name="automation_courtsms_submit",
            ),
            path(
                "<int:sms_id>/retry/",
                self.admin_site.admin_view(self.retry_single_sms_view),
                name="automation_courtsms_retry",
            ),
        ]
        return custom_urls + urls
