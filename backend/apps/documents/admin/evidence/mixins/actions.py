"""Module for actions."""

import logging
from typing import Any

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.documents.models import EvidenceList

from .views import EvidenceListAdminServiceMixin

logger = logging.getLogger(__name__)


class EvidenceListAdminActionsMixin(EvidenceListAdminServiceMixin):
    @admin.action(description=_("合并选中清单的 PDF"))
    def merge_pdfs(self, request, queryset) -> None:
        from django.contrib import messages

        from apps.documents.models import MergeStatus

        submitted_count = 0
        skipped_count = 0
        no_files_count = 0
        error_count = 0

        for evidence_list in queryset:
            try:
                if evidence_list.merge_status == MergeStatus.PROCESSING:
                    skipped_count += 1
                    continue

                items_with_files = evidence_list.items.filter(file__isnull=False).exclude(file="")
                if not items_with_files.exists():
                    no_files_count += 1
                    continue

                from apps.core.interfaces import ServiceLocator
                from apps.core.tasking import TaskContext

                task_name = f"merge_evidence_{evidence_list.id}"
                ServiceLocator.get_task_submission_service().submit(
                    "apps.documents.tasks.merge_evidence_pdf_task",
                    args=(evidence_list.id,),
                    task_name=task_name,
                    context=TaskContext(task_name=task_name, entity_id=str(evidence_list.id)),
                )
                EvidenceList.objects.filter(pk=evidence_list.id).update(
                    merge_status=MergeStatus.PROCESSING,
                    merge_progress=0,
                    merge_current=0,
                    merge_total=0,
                    merge_message="已提交合并任务",
                )
                submitted_count += 1
            except Exception as e:
                error_count += 1
                messages.warning(request, f"清单 {evidence_list.id} 提交失败: {e!s}")

        if submitted_count > 0:
            messages.success(request, f"已提交 {submitted_count} 个合并任务")
        if skipped_count > 0:
            messages.info(request, f"{skipped_count} 个清单正在合并中,已跳过")
        if no_files_count > 0:
            messages.warning(request, f"{no_files_count} 个清单没有文件,已跳过")
        if error_count > 0:
            messages.warning(request, f"{error_count} 个清单提交失败")

    @admin.action(description=_("导出选中清单的 Word"))
    def export_list_word(self, request, queryset) -> Any:
        from django.contrib import messages

        if queryset.count() > 1:
            messages.warning(request, "批量导出请逐个操作")
            return

        evidence_list = queryset.first()
        return self.export_list_view(request, evidence_list.pk)


__all__: list[str] = ["EvidenceListAdminActionsMixin"]
