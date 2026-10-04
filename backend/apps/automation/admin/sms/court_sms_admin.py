"""
法院短信处理 Django Admin 界面

提供短信记录管理、状态查看、手动处理等功能。
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from django.contrib import admin, messages
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.urls import path, reverse

from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

from .court_sms_admin_actions import CourtSMSAdminActions
from .court_sms_admin_base import CourtSMSAdminBase


@admin.register(CourtSMS)
class CourtSMSAdmin(CourtSMSAdminActions, CourtSMSAdminBase):  # pragma: no cover
    """法院短信管理（组合 Base + Actions）"""

    ordering = ("-received_at",)
    actions = ["retry_processing_action"]

    def get_urls(self) -> list[Any]:  # pragma: no cover
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
                "<int:sms_id>/recommendations/",
                self.admin_site.admin_view(self.recommendations_ajax),
                name="automation_courtsms_recommendations",
            ),
            path(
                "<int:sms_id>/documents/<int:ref_index>/open/",
                self.admin_site.admin_view(self.open_document_view),
                name="automation_courtsms_open_document",
            ),
            path(
                "<int:sms_id>/documents/<int:ref_index>/rename/",
                self.admin_site.admin_view(self.rename_document_view),
                name="automation_courtsms_rename_document",
            ),
            path(
                "<int:sms_id>/documents/download-all/",
                self.admin_site.admin_view(self.download_all_documents_view),
                name="automation_courtsms_download_all_documents",
            ),
            path(
                "<int:sms_id>/retry/",
                self.admin_site.admin_view(self.retry_single_sms_view),
                name="automation_courtsms_retry",
            ),
        ]
        return custom_urls + urls

    def open_document_view(self, request: HttpRequest, sms_id: int, ref_index: int) -> FileResponse:  # pragma: no cover
        """打开或下载关联文书文件"""
        sms = self.get_object(request, str(sms_id))
        if sms is None:
            raise Http404("SMS not found")

        references = CourtSMSDocumentReferenceService().collect(sms)
        if ref_index < 0 or ref_index >= len(references):
            raise Http404("Document reference not found")

        file_path = Path(references[ref_index].file_path)
        if not file_path.exists() or not file_path.is_file():
            raise Http404("Document file not found")

        as_attachment = request.GET.get("download") == "1"
        return FileResponse(file_path.open("rb"), as_attachment=as_attachment, filename=file_path.name)

    def download_all_documents_view(self, request: HttpRequest, sms_id: int) -> HttpResponseBase:  # pragma: no cover
        """批量下载关联文书（ZIP）"""
        sms = self.get_object(request, str(sms_id))
        if sms is None:
            raise Http404("SMS not found")

        references = CourtSMSDocumentReferenceService().collect(sms)
        if not references:
            messages.error(request, "当前短信没有可下载的关联文书")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        existing_files: list[Path] = []
        for ref in references:
            current = Path(ref.file_path)
            if current.exists() and current.is_file():
                existing_files.append(current)

        if not existing_files:
            messages.error(request, "关联文书文件不存在，无法批量下载")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        zip_buffer = io.BytesIO()
        name_count: dict[str, int] = {}
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in existing_files:
                base_name = file_path.name
                if base_name in name_count:
                    name_count[base_name] += 1
                    stem = file_path.stem
                    suffix = file_path.suffix
                    arcname = f"{stem}_{name_count[base_name]}{suffix}"
                else:
                    name_count[base_name] = 1
                    arcname = base_name
                zip_file.write(file_path, arcname=arcname)

        zip_buffer.seek(0)
        archive_name = f"courtsms_{sms_id}_documents.zip"
        return FileResponse(zip_buffer, as_attachment=True, filename=archive_name)

    def rename_document_view(
        self, request: HttpRequest, sms_id: int, ref_index: int
    ) -> HttpResponse:  # pragma: no cover
        """手动重命名关联文书（仅允许修改文件名）"""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        sms = self.get_object(request, str(sms_id))
        if sms is None:
            raise Http404("SMS not found")

        references = CourtSMSDocumentReferenceService().collect(sms)
        if ref_index < 0 or ref_index >= len(references):
            messages.error(request, "未找到目标文书")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        ref = references[ref_index]
        file_path = Path(ref.file_path)
        if not file_path.exists() or not file_path.is_file():
            messages.error(request, "文书文件不存在")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        raw_stem = str(request.POST.get("new_stem", "") or "").strip()
        if not raw_stem:
            messages.error(request, "文件名不能为空")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))
        if "." in raw_stem:
            messages.error(request, "只能修改文件名，不能修改文件格式")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        new_stem = self._sanitize_filename_stem(raw_stem)
        if not new_stem:
            messages.error(request, "文件名包含非法字符")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        old_abs = str(file_path.resolve())
        new_path = file_path.with_name(f"{new_stem}{file_path.suffix}")

        if new_path == file_path:
            messages.info(request, "文件名未变化")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        if new_path.exists():
            messages.error(request, f"目标文件已存在：{new_path.name}")
            return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

        file_path.rename(new_path)
        self._sync_document_references(sms, old_abs, str(new_path.resolve()), ref.court_document_id)

        messages.success(request, f"文书已重命名为：{new_path.name}")
        return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

    def _sanitize_filename_stem(self, value: str) -> str:  # pragma: no cover
        """清理文件名主体，去除路径与非法字符"""
        cleaned = value.replace("/", "").replace("\\", "").strip(" .")
        cleaned = re.sub(r'[<>:"|?*\x00-\x1f\x7f]', "", cleaned)
        return cleaned.strip()

    def _sync_document_references(  # pragma: no cover
        self,
        sms: CourtSMS,
        old_path: str,
        new_path: str,
        court_document_id: int | None,
    ) -> None:
        """同步重命名后的引用路径（薄委托，实现在 Service 层）"""
        CourtSMSDocumentReferenceService().sync_document_references(sms, old_path, new_path, court_document_id)
