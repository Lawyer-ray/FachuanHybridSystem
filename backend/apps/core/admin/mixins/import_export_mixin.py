"""Admin 导入导出公共 Mixin。"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger("apps.core")


class AdminImportExportMixin:
    """
    为 ModelAdmin 提供 JSON 导入导出功能。

    子类需实现：
    - export_model_name: str  （如 "client"）
    - handle_json_import(data: list[dict], user: str) -> tuple[int, int, list[str]]
      返回 (成功数, 跳过数, 错误列表)
    - serialize_queryset(queryset) -> list[dict]
    """

    export_model_name: str = "export"

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()  # type: ignore[misc]
        custom = [
            path("import/", self.admin_site.admin_view(self.import_view), name=f"{self.export_model_name}_import"),
        ]
        return custom + urls

    def import_view(self, request: HttpRequest) -> HttpResponse:
        if request.method == "GET":
            return render(request, "admin/import_form.html", {
                "title": _("导入 JSON"),
                "model_name": self.export_model_name,
                "opts": self.model._meta,  # type: ignore[attr-defined]
            })

        uploaded = request.FILES.get("json_file")
        if not uploaded:
            messages.error(request, _("请选择 JSON 文件"))
            return render(request, "admin/import_form.html", {
                "title": _("导入 JSON"),
                "model_name": self.export_model_name,
                "opts": self.model._meta,  # type: ignore[attr-defined]
            })

        try:
            raw = json.loads(uploaded.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            messages.error(request, _("JSON 解析失败: %(err)s") % {"err": str(exc)})
            return render(request, "admin/import_form.html", {
                "title": _("导入 JSON"),
                "model_name": self.export_model_name,
                "opts": self.model._meta,  # type: ignore[attr-defined]
            })

        data_list: list[dict[str, Any]] = raw if isinstance(raw, list) else [raw]
        user = str(request.user)
        success, skipped, errors = self.handle_json_import(data_list, user)  # type: ignore[attr-defined]

        messages.success(request, _("导入完成：成功 %(s)d 条，跳过 %(k)d 条") % {"s": success, "k": skipped})
        for err in errors:
            messages.warning(request, err)

        from django.shortcuts import redirect
        return redirect(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")  # type: ignore[attr-defined]

    def export_selected_as_json(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponse:
        data = self.serialize_queryset(queryset)  # type: ignore[attr-defined]
        count = len(data)
        filename = f"{self.export_model_name}_selected_{count}_export_{date.today().strftime('%Y%m%d')}.json"
        return self._json_response(data, filename)

    export_selected_as_json.short_description = _("导出选中为 JSON")  # type: ignore[attr-defined]

    def export_all_as_json(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponse:
        all_qs = self.get_queryset(request)  # type: ignore[attr-defined]
        data = self.serialize_queryset(all_qs)  # type: ignore[attr-defined]
        filename = f"{self.export_model_name}_all_export_{date.today().strftime('%Y%m%d')}.json"
        return self._json_response(data, filename)

    export_all_as_json.short_description = _("导出全部为 JSON")  # type: ignore[attr-defined]

    def _json_response(self, data: list[dict[str, Any]], filename: str) -> HttpResponse:
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        response = HttpResponse(content, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
