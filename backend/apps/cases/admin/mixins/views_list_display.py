"""案件 Admin 列表页的列展示方法。"""

from __future__ import annotations

import logging

from django.urls import reverse
from django.utils.html import format_html

from apps.cases.models import Case

logger = logging.getLogger("apps.cases")


class CaseAdminListDisplayMixin:  # pragma: no cover
    """案件列表页各列的渲染方法（只读展示，不触发业务写入）。"""

    def id_link(self, obj: Case) -> str:  # pragma: no cover
        change_url = reverse("admin:cases_case_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', change_url, obj.pk)

    id_link.short_description = "ID"  # type: ignore[attr-defined]
    id_link.admin_order_field = "id"  # type: ignore[attr-defined]

    def name_link(self, obj: Case) -> str:  # pragma: no cover
        detail_url = reverse("admin:cases_case_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', detail_url, obj.name)

    name_link.short_description = "案件名称"  # type: ignore[attr-defined]
    name_link.admin_order_field = "name"  # type: ignore[attr-defined]

    def case_type_display(self, obj: Case) -> str:  # pragma: no cover
        return obj.get_case_type_display() or "-"

    case_type_display.short_description = "案件类型"  # type: ignore[attr-defined]
    case_type_display.admin_order_field = "case_type"  # type: ignore[attr-defined]

    def current_stage_display(self, obj: Case) -> str:  # pragma: no cover
        return obj.get_current_stage_display() or "-"

    current_stage_display.short_description = "当前阶段"  # type: ignore[attr-defined]
    current_stage_display.admin_order_field = "current_stage"  # type: ignore[attr-defined]

    def assigned_lawyers(self, obj: Case) -> str:  # pragma: no cover
        lawyers = []
        for assignment in obj.assignments.all():
            lawyer = assignment.lawyer
            lawyers.append(lawyer.real_name if lawyer.real_name else str(lawyer.id))
        return ", ".join(lawyers) if lawyers else "-"

    assigned_lawyers.short_description = "承办律师"  # type: ignore[attr-defined]

    def contract_folder_path_display(self, obj: Case) -> str:  # pragma: no cover
        if not obj or not obj.contract:
            return "未关联合同"

        try:
            binding = getattr(obj.contract, "folder_binding", None)
            if binding and binding.folder_path:
                return str(binding.folder_path)
            return "未绑定文件夹"
        except (AttributeError, TypeError, ValueError):
            logger.warning("读取合同文件夹路径失败: case_id=%s", getattr(obj, "pk", None), exc_info=True)
            return "未绑定文件夹"

    contract_folder_path_display.short_description = "合同文件夹路径"  # type: ignore[attr-defined]

    def filing_number_display(self, obj: Case) -> str:  # pragma: no cover
        if obj and obj.filing_number:
            return str(obj.filing_number)
        return "未生成"

    filing_number_display.short_description = "建档编号"  # type: ignore[attr-defined]

    def has_folder_binding(self, obj: Case) -> str:  # pragma: no cover
        try:
            if hasattr(obj, "folder_binding") and obj.folder_binding:
                return "✓ 已绑定"
            return "未绑定"
        except (AttributeError, TypeError, ValueError):
            logger.warning("读取文件夹绑定状态失败: case_id=%s", getattr(obj, "pk", None), exc_info=True)
            return "未绑定"

    has_folder_binding.short_description = "文件夹绑定"  # type: ignore[attr-defined]

    def get_matched_folder_templates_display(self, obj: Case) -> str:  # pragma: no cover
        if not obj or not obj.case_type:
            return "未设置案件类型"
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        return str(service.get_matched_folder_templates(obj.case_type))

    get_matched_folder_templates_display.short_description = "匹配的文件夹模板"  # type: ignore[attr-defined]


__all__: list[str] = ["CaseAdminListDisplayMixin"]
