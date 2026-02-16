"""Module for views."""

import logging

from django.db import models
from django.http import FileResponse, Http404, HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.documents.models import (
    LIST_TYPE_PREVIOUS,
    DocumentCaseFileSubType,
    DocumentTemplateType,
    EvidenceList,
    ListType,
)

logger = logging.getLogger(__name__)


class EvidenceListAdminServiceMixin:
    def _get_admin_service(self) -> None:
        from apps.documents.services.evidence_admin_service import EvidenceAdminService

        return EvidenceAdminService()


class EvidenceListAdminViewsMixin(EvidenceListAdminServiceMixin):
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None) -> None:
        if request.method == "POST":
            logger.info(
                "EvidenceListAdmin changeform POST",
                extra={
                    "object_id": object_id,
                    "post_keys": [k for k in request.POST.keys() if not k.startswith("_")],
                    "file_keys": list[Any](request.FILES.keys()),
                },
            )
        response = super().changeform_view(request, object_id, form_url, extra_context)

        if request.method == "POST":
            logger.info(
                "EvidenceListAdmin changeform POST response",
                extra={"object_id": object_id, "status_code": getattr(response, "status_code", None)},
            )
        return response

    def total_pages_display(self, obj) -> None:
        if not obj.total_pages:
            return ""
        return obj.total_pages

    total_pages_display.short_description = _("总页数")
    total_pages_display.admin_order_field = "total_pages"

    def formfield_for_foreignkey(self, db_field, request, **kwargs) -> None:
        if db_field.name == "export_template":
            from apps.documents.models import DocumentTemplate

            kwargs["queryset"] = DocumentTemplate.objects.filter(
                is_active=True,
                template_type=DocumentTemplateType.CASE,
                case_sub_type=DocumentCaseFileSubType.EVIDENCE_MATERIALS,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs) -> None:
        form = super().get_form(request, obj=obj, **kwargs)
        if "export_template" not in form.base_fields:
            return form

        field = form.base_fields["export_template"]
        if not obj or not getattr(obj, "export_template_id", None):
            return form

        if field.queryset.filter(pk=obj.export_template_id).exists():
            return form

        from apps.documents.models import DocumentTemplate

        field.queryset = field.queryset | DocumentTemplate.objects.filter(pk=obj.export_template_id)
        return form

    def get_urls(self) -> None:
        urls = super().get_urls()
        custom_urls = [
            path(
                "next-list-type/<int: case_id>/",
                self.admin_site.admin_view(self.next_list_type_view),
                name="documents_evidencelist_next_list_type",
            ),
            path(
                "<int:pk>/merge/",
                self.admin_site.admin_view(self.merge_view),
                name="documents_evidencelist_merge",
            ),
            path(
                "<int:pk>/merge-status/",
                self.admin_site.admin_view(self.merge_status_view),
                name="documents_evidencelist_merge_status",
            ),
            path(
                "<int:pk>/export-list/",
                self.admin_site.admin_view(self.export_list_view),
                name="documents_evidencelist_export_list",
            ),
            path(
                "<int:pk>/download-pdf/",
                self.admin_site.admin_view(self.download_pdf_view),
                name="documents_evidencelist_download_pdf",
            ),
            path(
                "<int:pk>/reorder/",
                self.admin_site.admin_view(self.reorder_view),
                name="documents_evidencelist_reorder",
            ),
            path(
                "<int:pk>/recount-pages/",
                self.admin_site.admin_view(self.recount_pages_view),
                name="documents_evidencelist_recount_pages",
            ),
        ]
        return custom_urls + urls

    def next_list_type_view(self, request, case_id) -> None:
        from django.http import JsonResponse

        existing_types = set(EvidenceList.objects.filter(case_id=case_id).values_list("list_type", flat=True))

        next_type = None
        next_label = None
        for list_type, label in ListType.choices:
            if list_type not in existing_types:
                next_type = list_type
                next_label = label
                break

        if next_type:
            return JsonResponse(
                {
                    "success": True,
                    "list_type": next_type,
                    "label": next_label,
                }
            )
        else:
            return JsonResponse(
                {
                    "success": False,
                    "error": "该案件已创建所有证据清单类型(最多6个)",
                }
            )

    def case_display(self, obj) -> None:
        return obj.case.name

    case_display.short_description = _("案件")

    def item_count_display(self, obj) -> None:
        count = obj.items.count()
        return count

    item_count_display.short_description = _("证据数量")

    def page_range_display(self, obj) -> None:
        return obj.page_range_display

    page_range_display.short_description = _("页码范围")

    def order_range_display(self, obj) -> None:
        return obj.order_range_display

    order_range_display.short_description = _("序号范围")

    def has_merged_pdf_display(self, obj) -> None:
        from apps.documents.models import MergeStatus

        if obj.merge_status == MergeStatus.PROCESSING:
            progress = getattr(obj, "merge_progress", 0) or 0
            current = getattr(obj, "merge_current", 0) or 0
            total = getattr(obj, "merge_total", 0) or 0
            message = getattr(obj, "merge_message", "") or ""
            detail = f"{progress}% ({current}/{total})"
            if message:
                detail = f"{detail} {message}"
            return format_html('<span style="color: #1976d2;">⏳ 合并中... {}</span>', detail)
        elif obj.merge_status == MergeStatus.FAILED:
            return format_html(
                '<span style="color: #d32f2f;" title="{}">❌ 失败</span>',
                obj.merge_error or "未知错误",
            )
        elif obj.merged_pdf:
            return mark_safe('<span style="color: #2e7d32;">✓ 已合并</span>')
        return mark_safe('<span style="color: #999;">未合并</span>')

    has_merged_pdf_display.short_description = _("合并状态")

    def actions_display(self, obj) -> None:
        merge_url = reverse("admin:documents_evidencelist_merge", args=[obj.pk])
        export_list_url = reverse("admin:documents_evidencelist_export_list", args=[obj.pk])
        recount_url = reverse("admin:documents_evidencelist_recount_pages", args=[obj.pk])

        buttons = [
            format_html('<a class="button" href="{}" title="合并PDF">合并</a>', merge_url),
            format_html('<a class="button" href="{}" title="导出证据清单Word">导出清单</a>', export_list_url),
            format_html('<a class="button" href="{}" title="重新识别PDF页数">识别页数</a>', recount_url),
        ]

        if obj.merged_pdf:
            download_url = reverse("admin:documents_evidencelist_download_pdf", args=[obj.pk])
            buttons.append(
                format_html('<a class="button" href="{}" title="下载证据明细PDF">下载明细</a>', download_url)
            )

        return mark_safe(" ".join(str(b) for b in buttons))

    actions_display.short_description = _("操作")

    def merge_view(self, request, pk) -> None:
        from django.contrib import messages
        from django.http import JsonResponse
        from django.shortcuts import redirect
        from django.utils import timezone

        from apps.documents.models import MergeStatus

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        try:
            evidence_list = EvidenceList.objects.get(pk=pk)

            if evidence_list.merge_status == MergeStatus.PROCESSING:
                if is_ajax:
                    return JsonResponse({"success": False, "error": "正在合并中,请稍候..."})
                messages.warning(request, "正在合并中,请稍候...")
                return redirect("admin:documents_evidencelist_change", pk)

            items_with_files = evidence_list.items.filter(file__isnull=False).exclude(file="")
            if not items_with_files.exists():
                if is_ajax:
                    return JsonResponse({"success": False, "error": "证据清单没有任何文件,无法合并"})
                messages.error(request, "证据清单没有任何文件,无法合并")
                return redirect("admin:documents_evidencelist_change", pk)

            from apps.core.interfaces import ServiceLocator
            from apps.core.tasking import TaskContext

            task_name = f"merge_evidence_{pk}"
            ServiceLocator.get_task_submission_service().submit(
                "apps.documents.tasks.merge_evidence_pdf_task",
                args=(pk,),
                task_name=task_name,
                context=TaskContext(task_name=task_name, entity_id=str(pk)),
            )

            evidence_list.merge_status = MergeStatus.PROCESSING
            evidence_list.merge_started_at = timezone.now()
            evidence_list.merge_finished_at = None
            evidence_list.merge_error = ""
            evidence_list.merge_progress = 0
            evidence_list.merge_current = 0
            evidence_list.merge_total = items_with_files.count()
            evidence_list.merge_message = "任务已提交"
            evidence_list.save(
                update_fields=[
                    "merge_status",
                    "merge_started_at",
                    "merge_finished_at",
                    "merge_error",
                    "merge_progress",
                    "merge_current",
                    "merge_total",
                    "merge_message",
                ]
            )

            if is_ajax:
                return JsonResponse({"success": True, "message": "合并任务已提交"})

            messages.info(request, "已提交合并任务,请稍候刷新页面查看结果...")

        except EvidenceList.DoesNotExist:
            if is_ajax:
                return JsonResponse({"success": False, "error": "证据清单不存在"})
            messages.error(request, "证据清单不存在")
        except Exception as e:
            logger.exception("操作失败")
            if is_ajax:
                return JsonResponse({"success": False, "error": f"提交合并任务失败: {e!s}"})
            messages.error(request, f"提交合并任务失败: {e!s}")

        return redirect("admin:documents_evidencelist_change", pk)

    def merge_status_view(self, request, pk) -> None:
        from django.http import JsonResponse

        try:
            evidence_list = EvidenceList.objects.select_related("case").get(pk=pk)
        except EvidenceList.DoesNotExist:
            return JsonResponse({"error": "证据清单不存在"}, status=404)

        pdf_filename = ""
        if evidence_list.merged_pdf:
            admin_service = self._get_admin_service()
            pdf_filename = admin_service.generate_pdf_filename(evidence_list)

        return JsonResponse(
            {
                "id": evidence_list.id,
                "status": evidence_list.merge_status,
                "progress": evidence_list.merge_progress,
                "current": evidence_list.merge_current,
                "total": evidence_list.merge_total,
                "message": evidence_list.merge_message,
                "error": evidence_list.merge_error,
                "started_at": evidence_list.merge_started_at.isoformat() if evidence_list.merge_started_at else None,
                "finished_at": evidence_list.merge_finished_at.isoformat() if evidence_list.merge_finished_at else None,
                "total_pages": evidence_list.total_pages,
                "has_pdf": bool(evidence_list.merged_pdf),
                "pdf_filename": pdf_filename,
            }
        )

    def export_list_view(self, request, pk) -> None:
        try:
            evidence_list = EvidenceList.objects.get(pk=pk)
            admin_service = self._get_admin_service()

            if evidence_list.export_template_id:
                content, filename = admin_service.export_list_word_with_template(pk, evidence_list.export_template_id)
            else:
                content, filename = admin_service.export_list_word(pk)

            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            from urllib.parse import quote

            encoded_filename = quote(filename)
            response["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
            return response
        except EvidenceList.DoesNotExist:
            raise Http404("证据清单不存在") from None
        except Exception as e:
            import traceback

            error_detail = f"{e!s}\n\n{traceback.format_exc()}"
            logger.error("导出失败", extra={"pk": pk, "error": error_detail}, exc_info=True)
            raise Http404(f"导出失败: {e!s}") from e

    def download_pdf_view(self, request, pk) -> None:
        try:
            admin_service = self._get_admin_service()
            evidence_list = EvidenceList.objects.select_related("case").get(pk=pk)
            if not evidence_list.merged_pdf:
                raise Http404("尚未合并 PDF,请先点击「合并」按钮")

            filename = admin_service.generate_pdf_filename(evidence_list)

            return FileResponse(
                evidence_list.merged_pdf.open("rb"),
                as_attachment=True,
                filename=filename,
            )
        except EvidenceList.DoesNotExist:
            raise Http404("证据清单不存在") from None

    def reorder_view(self, request, pk) -> None:
        import json

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        try:
            data = json.loads(request.body)
            item_ids = data.get("item_ids", [])

            admin_service = self._get_admin_service()
            admin_service.reorder_items(pk, item_ids)

            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("EvidenceList reorder 失败", extra={"evidence_list_id": pk, "error": str(e)})
            return JsonResponse({"error": str(e)}, status=400)

    def recount_pages_view(self, request, pk) -> None:
        from django.contrib import messages
        from django.shortcuts import redirect

        try:
            admin_service = self._get_admin_service()
            result = admin_service.recount_pages(pk)

            if result["updated"] > 0:
                messages.success(request, f"已重新识别 {result['updated']} 个文件的页数,总页数:{result['total_pages']}")
            else:
                messages.info(request, "没有需要更新的文件")

            if result.get("errors"):
                for error in result["errors"]:
                    messages.warning(request, error)

        except EvidenceList.DoesNotExist:
            messages.error(request, "证据清单不存在")
        except Exception as e:
            logger.exception("EvidenceList recount_pages 失败", extra={"evidence_list_id": pk, "error": str(e)})
            messages.error(request, f"识别页数失败: {e!s}")

        return redirect("admin:documents_evidencelist_changelist")


__all__: list[str] = ["EvidenceListAdminServiceMixin", "EvidenceListAdminViewsMixin"]
