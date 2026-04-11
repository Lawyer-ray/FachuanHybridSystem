"""
法院短信处理 Django Admin 界面

提供短信记录管理、状态查看、手动处理等功能。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.contrib import admin
from django.http import FileResponse, Http404, HttpRequest
from django.urls import path

from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

from .court_sms_admin_actions import CourtSMSAdminActions
from .court_sms_admin_base import CourtSMSAdminBase


@admin.register(CourtSMS)
class CourtSMSAdmin(CourtSMSAdminActions, CourtSMSAdminBase):
    """法院短信管理（组合 Base + Actions）"""

    ordering = ("-received_at",)
    actions = ["retry_processing_action"]

    def get_urls(self) -> list[Any]:
        """添加自定义 URL"""
        urls: list[Any] = list(super().get_urls())
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
                "<int:sms_id>/documents/<int:ref_index>/open/",
                self.admin_site.admin_view(self.open_document_view),
                name="automation_courtsms_open_document",
            ),
            path(
                "<int:sms_id>/retry/",
                self.admin_site.admin_view(self.retry_single_sms_view),
                name="automation_courtsms_retry",
            ),
        ]
        return custom_urls + urls

    def open_document_view(self, request: HttpRequest, sms_id: int, ref_index: int) -> FileResponse:
        """打开关联文书文件"""
        sms = self.get_object(request, str(sms_id))
        if sms is None:
            raise Http404("SMS not found")

        references = CourtSMSDocumentReferenceService().collect(sms)
        if ref_index < 0 or ref_index >= len(references):
            raise Http404("Document reference not found")

        file_path = Path(references[ref_index].file_path)
        if not file_path.exists() or not file_path.is_file():
            raise Http404("Document file not found")

        return FileResponse(file_path.open("rb"), as_attachment=False, filename=file_path.name)
