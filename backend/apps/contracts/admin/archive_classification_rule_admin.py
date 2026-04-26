"""归档分类学习规则 Admin 配置。"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import ArchiveClassificationRule

logger = logging.getLogger(__name__)


@admin.register(ArchiveClassificationRule)
class ArchiveClassificationRuleAdmin(admin.ModelAdmin):
    list_display = ("archive_category", "filename_keyword", "archive_item_code", "hit_count", "source", "updated_at")
    list_filter = ("archive_category", "source")
    search_fields = ("filename_keyword", "archive_item_code")
    readonly_fields = ("hit_count", "created_at", "updated_at")
    actions = ["export_selected_rules_to_code"]

    def get_urls(self) -> list[Any]:
        from django.urls import path as urlpath

        urls = super().get_urls()
        custom = [
            urlpath(
                "learn-from-archived/",
                self.admin_site.admin_view(self.learn_from_archived_view),
                name="contracts_archiveclassificationrule_learn",
            ),
            urlpath(
                "export-to-code/",
                self.admin_site.admin_view(self.export_to_code_view),
                name="contracts_archiveclassificationrule_export",
            ),
        ]
        return custom + urls

    def learn_from_archived_view(self, request: HttpRequest) -> JsonResponse:
        """从已归档材料中学习分类规则。"""
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        try:
            from apps.contracts.services.archive.learning_service import ArchiveLearningService

            service = ArchiveLearningService()
            result = service.learn_from_archived_materials()
            return JsonResponse(
                {
                    "success": True,
                    "message": _("学习完成：新增 %(learned)d 条，更新 %(updated)d 条，跳过 %(skipped)d 条") % result,
                    **result,
                }
            )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.exception("archive_learning_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def export_to_code_view(self, request: HttpRequest) -> JsonResponse:
        """将学习规则导出为代码文件。"""
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        try:
            from apps.contracts.services.archive.learning_service import ArchiveLearningService

            service = ArchiveLearningService()
            result = service.export_rules_to_code()
            return JsonResponse(
                {
                    "success": True,
                    "message": _("导出完成：%(rule_count)d 条规则，%(category_count)d 个分类") % result,
                    **result,
                }
            )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.exception("archive_rules_export_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    @admin.action(description=_("导出选中规则到代码文件"))
    def export_selected_rules_to_code(self, request: HttpRequest, queryset: Any) -> None:
        """Admin action：导出选中规则到代码文件。"""
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        service = ArchiveLearningService()
        result = service.export_rules_to_code()
        self.message_user(
            request,
            _("导出完成：%(rule_count)d 条规则，%(category_count)d 个分类") % result,
        )
