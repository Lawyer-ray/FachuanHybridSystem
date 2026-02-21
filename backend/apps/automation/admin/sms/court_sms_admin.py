"""
法院短信处理 Django Admin 界面

提供短信记录管理、状态查看、手动处理等功能。
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path

from apps.automation.models import CourtSMS

from .court_sms_admin_actions import CourtSMSAdminActions
from .court_sms_admin_base import CourtSMSAdminBase
from .court_sms_admin_themed_views import CourtSMSAdminThemedViews


@admin.register(CourtSMS)
class CourtSMSAdmin(CourtSMSAdminThemedViews, CourtSMSAdminActions, CourtSMSAdminBase):
    """法院短信管理（组合 Base + Actions + ThemedViews）"""

    ordering: ClassVar[list[str]] = ["-received_at"]
    actions: ClassVar[list[str]] = ["retry_processing_action"]

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
                "<int:sms_id>/assign-case/",
                self.admin_site.admin_view(self.assign_case_view),
                name="automation_courtsms_assign_case",
            ),
            path(
                "<int:sms_id>/search-cases/",
                self.admin_site.admin_view(self.search_cases_ajax),
                name="automation_courtsms_search_cases",
            ),
            path(
                "<int:sms_id>/retry/",
                self.admin_site.admin_view(self.retry_single_sms_view),
                name="automation_courtsms_retry",
            ),
        ]
        # 注册 add2 ~ add41 主题视图
        for n in range(2, 42):
            custom_urls.append(
                path(
                    f"add{n}/",
                    self.admin_site.admin_view(
                        lambda req, _n=n: self._add_numbered_view(req, _n)
                    ),
                    name=f"automation_courtsms_add{n}",
                )
            )
        return custom_urls + urls

    def _add_numbered_view(self, request: HttpRequest, n: int) -> HttpResponse:
        """通用主题视图分发器，委托给对应的 add{n}_view 方法"""
        method = getattr(self, f"add{n}_view", None)
        if method is None:
            from django.http import Http404
            raise Http404(f"add{n}_view not found")
        return method(request)  # type: ignore[no-any-return]
