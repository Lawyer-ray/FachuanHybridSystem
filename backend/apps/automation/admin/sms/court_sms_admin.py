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

from django.conf import settings
from django.contrib import admin, messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse

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

    def open_document_view(self, request: HttpRequest, sms_id: int, ref_index: int) -> FileResponse:
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

    def download_all_documents_view(self, request: HttpRequest, sms_id: int) -> HttpResponse:
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

    def rename_document_view(self, request: HttpRequest, sms_id: int, ref_index: int) -> HttpResponse:
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

    def _sanitize_filename_stem(self, value: str) -> str:
        """清理文件名主体，去除路径与非法字符"""
        cleaned = value.replace("/", "").replace("\\", "").strip(" .")
        cleaned = re.sub(r'[<>:"|?*\x00-\x1f\x7f]', "", cleaned)
        return cleaned.strip()

    def _normalize_path_like(self, raw_path: str | Path | None) -> str:
        """将相对/绝对路径统一为规范绝对路径（不要求文件存在）"""
        path = Path(str(raw_path or ""))
        if not path.is_absolute():
            path = Path(settings.MEDIA_ROOT) / path
        return str(path.resolve(strict=False))

    def _sync_document_references(
        self,
        sms: CourtSMS,
        old_path: str,
        new_path: str,
        court_document_id: int | None,
    ) -> None:
        """同步重命名后的引用路径，保证后续下载命中新文件名"""
        old_norm = self._normalize_path_like(old_path)
        new_norm = self._normalize_path_like(new_path)

        self._sync_sms_document_paths(sms, old_norm, new_norm)
        self._sync_scraper_result_paths(sms, old_norm, new_norm)
        self._sync_case_log_attachment_paths(sms, old_norm, new_norm)

        if court_document_id:
            from apps.automation.models import CourtDocument

            CourtDocument.objects.filter(id=court_document_id).update(local_file_path=new_norm)

    def _sync_sms_document_paths(self, sms: CourtSMS, old_norm: str, new_norm: str) -> None:
        paths = sms.document_file_paths if isinstance(sms.document_file_paths, list) else []
        changed = False
        updated_paths: list[str] = []

        for raw in paths:
            current = str(raw)
            if self._normalize_path_like(current) == old_norm:
                updated_paths.append(new_norm)
                changed = True
            else:
                updated_paths.append(current)

        if changed:
            sms.document_file_paths = updated_paths
            sms.save(update_fields=["document_file_paths", "updated_at"])

    def _sync_scraper_result_paths(self, sms: CourtSMS, old_norm: str, new_norm: str) -> None:
        task = sms.scraper_task
        if not task or not isinstance(task.result, dict):
            return

        result = task.result
        changed = False

        for key in ("files", "renamed_files"):
            values = result.get(key)
            if not isinstance(values, list):
                continue
            updated: list[str] = []
            key_changed = False
            for raw in values:
                current = str(raw)
                if self._normalize_path_like(current) == old_norm:
                    updated.append(new_norm)
                    key_changed = True
                else:
                    updated.append(current)
            if key_changed:
                result[key] = updated
                changed = True

        if changed:
            task.result = result
            task.save(update_fields=["result", "updated_at"])

    def _sync_case_log_attachment_paths(self, sms: CourtSMS, old_norm: str, new_norm: str) -> None:
        if not sms.case_log:
            return

        media_root = Path(settings.MEDIA_ROOT).resolve()
        new_path = Path(new_norm).resolve(strict=False)

        try:
            relative_new_path = new_path.relative_to(media_root).as_posix()
        except ValueError:
            return

        attachments = getattr(sms.case_log, "attachments", None)
        if attachments is None:
            return

        for attachment in attachments.all():
            file_obj = getattr(attachment, "file", None)
            if not file_obj:
                continue

            current_raw = getattr(file_obj, "path", "") or getattr(file_obj, "name", "")
            if self._normalize_path_like(current_raw) != old_norm:
                continue

            attachment.file.name = relative_new_path
            attachment.save(update_fields=["file"])
