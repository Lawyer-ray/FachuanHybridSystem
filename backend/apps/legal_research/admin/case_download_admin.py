"""案例下载 Admin"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from apps.core.interfaces import ServiceLocator
from apps.legal_research.models import (
    CaseDownloadFormat,
    CaseDownloadResult,
    CaseDownloadStatus,
    CaseDownloadTask,
)
from apps.legal_research.services.case_download_service import CaseDownloadService

logger = logging.getLogger(__name__)


class CaseDownloadResultInline(admin.TabularInline[CaseDownloadResult, CaseDownloadTask]):
    model = CaseDownloadResult
    extra = 0
    readonly_fields = [
        "case_number",
        "status",
        "file_size",
        "error_message",
        "download_link",
    ]
    can_delete = False
    fields = readonly_fields
    verbose_name_plural = "下载结果"
    verbose_name = "下载结果"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="文件")
    def download_link(self, obj: CaseDownloadResult) -> str:
        if obj.status != "success":
            return "—"
        return format_html(
            '<a href="{}" target="_blank">下载</a>',
            reverse("admin:legal_research_casedownloadresult_download", args=[obj.pk]),
        )


@admin.register(CaseDownloadTask)
class CaseDownloadTaskAdmin(admin.ModelAdmin[CaseDownloadTask]):
    WEIKE_SITE_FILTER = (
        Q(site_name__icontains="wkxx")
        | Q(site_name__iexact="wk")
        | Q(site_name__icontains="威科先行")
        | Q(site_name__icontains="威科")
        | Q(site_name__icontains="weike")
        | Q(site_name__icontains="wkinfo")
        | Q(url__icontains="wkinfo.com.cn")
    )

    list_display: ClassVar[list[str]] = [
        "id",
        "file_format",
        "status",
        "total_count",
        "success_count",
        "failed_count",
        "credential",
        "created_at",
        "action_buttons",
    ]
    list_filter: ClassVar[list[str]] = ["status", "file_format", "created_at"]
    search_fields: ClassVar[tuple[str, ...]] = (
        "id",
        "case_numbers",
        "credential__account",
        "credential__site_name",
    )
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "created_by",
        "credential",
        "status",
        "total_count",
        "success_count",
        "failed_count",
        "message",
        "error",
        "q_task_id",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ]
    ordering: ClassVar[list[str]] = ["-created_at"]
    inlines: ClassVar[list[type[admin.TabularInline]]] = [CaseDownloadResultInline]
    actions: ClassVar[list[str]] = ["download_as_zip", "retry_failed"]

    def get_urls(self):  # type: ignore[override]
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "<path:object_id>/download/",
                self.admin_site.admin_view(self.download_zip_view),
                name=f"{opts.app_label}_{opts.model_name}_download_zip",
            ),
            path(
                "<path:object_id>/retry/",
                self.admin_site.admin_view(self.retry_view),
                name=f"{opts.app_label}_{opts.model_name}_retry",
            ),
        ]
        return custom_urls + urls

    def get_fields(self, request, obj: CaseDownloadTask | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            return ["credential", "case_numbers", "file_format"]
        return list(self.readonly_fields)

    def get_readonly_fields(self, request, obj: CaseDownloadTask | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            return []
        return list(self.readonly_fields)

    def get_form(self, request, obj: CaseDownloadTask | None = None, **kwargs):  # type: ignore[override]
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            self._configure_credential_field(request, form)
            self._configure_case_numbers_field(form)
            self._configure_file_format_field(form)
        return form

    @staticmethod
    def _configure_credential_field(request, form: type[forms.ModelForm]) -> None:
        credential_field = form.base_fields.get("credential")
        if credential_field is None:
            return

        queryset = AccountCredential.objects.select_related("lawyer", "lawyer__law_firm").filter(
            Q(site_name__icontains="wkxx")
            | Q(site_name__iexact="wk")
            | Q(site_name__icontains="威科先行")
            | Q(site_name__icontains="威科")
            | Q(site_name__icontains="weike")
            | Q(site_name__icontains="wkinfo")
            | Q(url__icontains="wkinfo.com.cn")
        )
        user = getattr(request, "user", None)
        if not getattr(user, "is_superuser", False):
            is_lawyer_user = getattr(getattr(user, "_meta", None), "label_lower", "") == "organization.lawyer"
            if is_lawyer_user:
                queryset = queryset.filter(lawyer__law_firm_id=getattr(user, "law_firm_id", None))
            else:
                queryset = queryset.none()

        credential_field.queryset = queryset
        if queryset.count() == 1:
            only = queryset.first()
            if only is not None:
                credential_field.initial = only.id
        elif queryset.count() == 0:
            credential_field.help_text = "没有可用的wkxx账号，请先在账号密码中添加"
        else:
            credential_field.help_text = "仅显示wkxx账号"

    @staticmethod
    def _configure_case_numbers_field(form: type[forms.ModelForm]) -> None:
        case_numbers_field = form.base_fields.get("case_numbers")
        if case_numbers_field is None:
            return
        case_numbers_field.help_text = (
            "支持多种分隔格式：换行、逗号(,)、中文逗号(，)、分号(;)。"
            "例如：<br/>"
            "(2024)粤0605民初3356号<br/>"
            "(2024)粤0605民初3356号, (2024)粤0305民初1234号<br/>"
            "(2024)粤0605民初3356号； (2024)粤0305民初1234号"
        )
        if hasattr(case_numbers_field.widget, "attrs"):
            case_numbers_field.widget.attrs["rows"] = "6"
            case_numbers_field.widget.attrs["placeholder"] = (
                "输入案号，支持多种分隔格式：\n"
                "(2024)粤0605民初3356号\n"
                "(2024)粤0605民初3356号, (2024)粤0305民初1234号"
            )

    @staticmethod
    def _configure_file_format_field(form: type[forms.ModelForm]) -> None:
        file_format_field = form.base_fields.get("file_format")
        if file_format_field is None:
            return
        file_format_field.initial = CaseDownloadFormat.PDF
        file_format_field.help_text = "选择下载的文档格式，默认PDF格式"

    def save_model(self, request, obj: CaseDownloadTask, form, change) -> None:  # type: ignore[override]
        if change:
            super().save_model(request, obj, form, change)
            return

        # 设置创建者
        user = getattr(request, "user", None)
        is_lawyer_user = getattr(getattr(user, "_meta", None), "label_lower", "") == "organization.lawyer"
        if obj.created_by_id is None and is_lawyer_user and getattr(user, "id", None) is not None:
            obj.created_by_id = int(request.user.id)

        super().save_model(request, obj, form, change)

        # 提交到队列
        try:
            q_task_id = ServiceLocator.get_task_submission_service().submit(
                "apps.legal_research.tasks.execute_case_download_task",
                args=[obj.id],
                task_name=f"case_download_{obj.id}",
                timeout=3600,
            )
            obj.q_task_id = q_task_id
            obj.status = CaseDownloadStatus.QUEUED
            obj.message = "任务已提交到队列"
            obj.save(update_fields=["q_task_id", "status", "message", "updated_at"])
            messages.success(request, "案例下载任务已提交到队列")
        except Exception as exc:
            logger.exception("提交案例下载任务失败", extra={"task_id": obj.id})
            obj.status = CaseDownloadStatus.FAILED
            obj.error = str(exc)
            obj.save(update_fields=["status", "error", "updated_at"])
            messages.error(request, f"任务创建成功但提交队列失败: {exc}")

    def delete_model(self, request, obj: CaseDownloadTask) -> None:
        # 先删除文件
        deleted_count = CaseDownloadService.delete_task_files(task_id=obj.id)
        logger.info("删除案例下载任务文件", extra={"task_id": obj.id, "deleted_files": deleted_count})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset) -> None:
        for obj in queryset:
            deleted_count = CaseDownloadService.delete_task_files(task_id=obj.id)
            logger.info("删除案例下载任务文件", extra={"task_id": obj.id, "deleted_files": deleted_count})
        super().delete_queryset(request, queryset)

    @admin.action(description="打包下载选中任务")
    def download_as_zip(self, request, queryset) -> None:
        if queryset.count() == 1:
            obj = queryset.first()
            if obj is None:
                return
            zip_path, msg = CaseDownloadService.download_task_as_zip(task_id=obj.id)
            if zip_path is None:
                messages.error(request, msg)
                return

            from django.http import FileResponse
            from pathlib import Path

            response: HttpResponse = FileResponse(
                open(zip_path, "rb"),
                as_attachment=True,
                filename=f"案例下载_{obj.id}.zip",
            )
            # 清理临时 zip 文件
            try:
                Path(zip_path).unlink(missing_ok=True)
            except Exception:
                pass
            return

        # 多个任务打包
        import zipfile
        from pathlib import Path
        from django.conf import settings
        from datetime import datetime

        zip_filename = f"案例下载_批量_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
        zip_path = Path(settings.MEDIA_ROOT) / "legal_research" / "case_download" / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for obj in queryset:
                results = obj.results.filter(status="success")
                for result in results:
                    file_path = Path(result.file_path)
                    if file_path.exists():
                        safe_name = result.case_number.replace("(", "").replace(")", "").replace(" ", "_")
                        ext = file_path.suffix.lstrip(".")
                        zf.write(file_path, f"{obj.id}/{safe_name}.{ext}")

        response: HttpResponse = FileResponse(
            open(zip_path, "rb"),
            as_attachment=True,
            filename=zip_filename,
        )
        try:
            Path(zip_path).unlink(missing_ok=True)
        except Exception:
            pass
        return

    @admin.action(description="重试失败项")
    def retry_failed(self, request, queryset) -> None:
        for obj in queryset:
            failed_results = obj.results.filter(status="failed")
            if not failed_results.exists():
                messages.warning(request, f"任务 {obj.id} 没有失败项可重试")
                continue

            # 更新案号列表为失败的案号
            failed_case_numbers = [r.case_number for r in failed_results]
            case_numbers_text = "\n".join(failed_case_numbers)

            # 创建新任务
            new_task = CaseDownloadService.create_task(
                created_by=obj.created_by,
                credential=obj.credential,
                case_numbers_text=case_numbers_text,
                file_format=obj.file_format,
            )

            # 提交到队列
            try:
                q_task_id = ServiceLocator.get_task_submission_service().submit(
                    "apps.legal_research.tasks.execute_case_download_task",
                    args=[new_task.id],
                    task_name=f"case_download_{new_task.id}",
                    timeout=3600,
                )
                new_task.q_task_id = q_task_id
                new_task.status = CaseDownloadStatus.QUEUED
                new_task.save(update_fields=["q_task_id", "status", "updated_at"])
                messages.success(request, f"任务 {obj.id} 的 {len(failed_case_numbers)} 个失败项已提交新任务 {new_task.id}")
            except Exception as exc:
                new_task.delete()
                messages.error(request, f"任务 {obj.id} 重试失败: {exc}")

    @admin.display(description="操作")
    def action_buttons(self, obj: CaseDownloadTask) -> str:
        buttons = []

        if obj.status == CaseDownloadStatus.COMPLETED and obj.success_count > 0:
            download_url = reverse("admin:legal_research_casedownloadtask_download_zip", args=[obj.pk])
            buttons.append(
                f'<a href="{download_url}" target="_blank" style="margin-right:8px;">打包下载</a>'
            )

        if obj.status in (CaseDownloadStatus.FAILED, CaseDownloadStatus.COMPLETED):
            retry_url = reverse("admin:legal_research_casedownloadtask_retry", args=[obj.pk])
            buttons.append(f'<a href="{retry_url}" style="margin-right:8px;">重试失败项</a>')

        if obj.status == CaseDownloadStatus.RUNNING:
            buttons.append('<span style="color:#1677ff;">执行中...</span>')

        if not buttons:
            return "—"
        return "".join(buttons)

    def download_zip_view(self, request, object_id) -> HttpResponse:
        obj = self.get_object(request, object_id)
        if obj is None:
            messages.error(request, "任务不存在")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadtask_changelist"))

        zip_path, msg = CaseDownloadService.download_task_as_zip(task_id=obj.id)
        if zip_path is None:
            messages.error(request, msg)
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadtask_change", args=[obj.pk]))

        from pathlib import Path
        from django.http import FileResponse

        response: HttpResponse = FileResponse(
            open(zip_path, "rb"),
            as_attachment=True,
            filename=f"案例下载_{obj.id}.zip",
        )
        try:
            Path(zip_path).unlink(missing_ok=True)
        except Exception:
            pass
        return response

    def retry_view(self, request, object_id) -> HttpResponse:
        obj = self.get_object(request, object_id)
        if obj is None:
            messages.error(request, "任务不存在")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadtask_changelist"))

        failed_results = obj.results.filter(status="failed")
        if not failed_results.exists():
            messages.warning(request, "没有失败项可重试")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadtask_change", args=[obj.pk]))

        failed_case_numbers = [r.case_number for r in failed_results]
        case_numbers_text = "\n".join(failed_case_numbers)

        new_task = CaseDownloadService.create_task(
            created_by=obj.created_by,
            credential=obj.credential,
            case_numbers_text=case_numbers_text,
            file_format=obj.file_format,
        )

        try:
            q_task_id = ServiceLocator.get_task_submission_service().submit(
                "apps.legal_research.tasks.execute_case_download_task",
                args=[new_task.id],
                task_name=f"case_download_{new_task.id}",
                timeout=3600,
            )
            new_task.q_task_id = q_task_id
            new_task.status = CaseDownloadStatus.QUEUED
            new_task.save(update_fields=["q_task_id", "status", "updated_at"])
            messages.success(request, f"已提交新任务 {new_task.id}，重试 {len(failed_case_numbers)} 个失败项")
        except Exception as exc:
            new_task.delete()
            messages.error(request, f"重试失败: {exc}")

        return HttpResponseRedirect(reverse("admin:legal_research_casedownloadtask_changelist"))


@admin.register(CaseDownloadResult)
class CaseDownloadResultAdmin(admin.ModelAdmin[CaseDownloadResult]):
    list_display: ClassVar[list[str]] = [
        "id",
        "task",
        "case_number",
        "title",
        "file_format",
        "file_size",
        "status",
        "downloaded_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "file_format", "downloaded_at"]
    search_fields: ClassVar[tuple[str, ...]] = ["case_number", "title", "court"]
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "task",
        "case_number",
        "title",
        "court",
        "judgment_date",
        "file_path",
        "file_size",
        "file_format",
        "status",
        "error_message",
        "downloaded_at",
    ]
    ordering: ClassVar[list[str]] = ["-downloaded_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def get_urls(self):  # type: ignore[override]
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "<path:object_id>/download/",
                self.admin_site.admin_view(self.download_file_view),
                name=f"{opts.app_label}_{opts.model_name}_download",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="文件")
    def file_link(self, obj: CaseDownloadResult) -> str:
        if obj.status != "success":
            return "—"
        return format_html(
            '<a href="{}" target="_blank">下载</a>',
            reverse("admin:legal_research_casedownloadresult_download", args=[obj.pk]),
        )

    def download_file_view(self, request, object_id) -> HttpResponse:
        try:
            result = CaseDownloadResult.objects.get(id=object_id)
        except CaseDownloadResult.DoesNotExist:
            messages.error(request, "结果不存在")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadresult_changelist"))

        if result.status != "success":
            messages.error(request, "文件下载失败，无可下载的文件")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadresult_changelist"))

        from pathlib import Path

        file_path = Path(result.file_path)
        if not file_path.exists():
            messages.error(request, "文件不存在，可能已被删除")
            return HttpResponseRedirect(reverse("admin:legal_research_casedownloadresult_changelist"))

        from django.http import FileResponse

        safe_name = result.case_number.replace("(", "").replace(")", "").replace(" ", "_")
        filename = f"{safe_name}{file_path.suffix}"

        response: HttpResponse = FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=filename,
        )
        return response


# 避免循环导入
from apps.organization.models import AccountCredential
