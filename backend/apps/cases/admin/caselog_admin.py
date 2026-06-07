from __future__ import annotations

import json
from typing import Any

from django.contrib import admin
from django.db import transaction
from django.forms import ModelForm
from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path as urlpath
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base_admin import BaseModelAdmin, BaseTabularInline
from apps.cases.models import CaseLog, CaseLogAttachment


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    extra = 0
    fields = ("file", "original_filename", "uploaded_at")
    readonly_fields = ("original_filename", "uploaded_at")
    autocomplete_fields = ("log",)


class ReminderInline(BaseTabularInline):
    model = CaseLog.reminders.rel.related_model  # type: ignore[assignment]  # Reminder
    extra = 0
    fields = ("reminder_type", "content", "due_at")
    verbose_name = "重要日期提醒"
    verbose_name_plural = "重要日期提醒"
    ordering = ("due_at",)


@admin.register(CaseLog)
class CaseLogAdmin(BaseModelAdmin):
    list_display = ("id", "case_link", "actor", "reminder_type", "reminder_time", "created_at", "updated_at")
    list_select_related = ("case", "actor")
    list_per_page = 50
    list_filter = ("created_at",)
    search_fields = ("content", "case__name")
    ordering = ("-created_at",)
    autocomplete_fields = ("case", "actor")
    exclude = ("actor", "source_subfolder")
    inlines = (ReminderInline, CaseLogAttachmentInline)
    change_list_template = "admin/cases/caselog/change_list.html"
    change_form_template = "admin/cases/caselog/change_form.html"

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> Any:
        """覆写 changelist：批量预填充 reminder 缓存，消除每行 2 次 DB 查询的 N+1。"""
        response = super().changelist_view(request, extra_context)

        # changelist_instance 在 super() 调用后可用
        cl = getattr(self, "changelist_instance", None)
        if cl is None or not hasattr(cl, "result_list") or not cl.result_list:
            return response

        case_log_ids = [obj.pk for obj in cl.result_list if obj.pk]
        if not case_log_ids:
            return response

        from apps.core.service_locator import ServiceLocator

        svc = ServiceLocator.get_reminder_service()
        batch = svc.export_case_log_reminders_batch_internal(case_log_ids=case_log_ids)

        for obj in cl.result_list:
            reminders = batch.get(obj.pk, [])
            # batch 按 due_at ASC, id ASC 排序，最后一条即最新
            latest = reminders[-1] if reminders else None
            obj._cached_latest_reminder = latest
            obj._cached_exported_reminders = reminders

        return response

    @admin.display(description="案件名称", ordering="case__name")
    def case_link(self, obj: CaseLog) -> str:
        url = reverse("admin:cases_case_detail", args=[obj.case_id])
        return format_html('<a href="{}">{}</a>', url, obj.case)

    def save_model(
        self,
        request: HttpRequest,
        obj: CaseLog,
        form: ModelForm[CaseLog],
        change: bool,
    ) -> None:
        if not getattr(obj, "actor_id", None):
            user_id = getattr(request.user, "id", None)
            if user_id is not None:
                obj.actor_id = user_id
        super().save_model(request, obj, form, change)

    # ── 批量添加日志 ──────────────────────────────────────────

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            urlpath(
                "batch-add/",
                self.admin_site.admin_view(self.batch_add_view),
                name="cases_caselog_batch_add",
            ),
            urlpath(
                "batch-add/cases/",
                self.admin_site.admin_view(self.batch_add_cases_view),
                name="cases_caselog_batch_add_cases",
            ),
            urlpath(
                "batch-add/search/",
                self.admin_site.admin_view(self.batch_add_search_view),
                name="cases_caselog_batch_add_search",
            ),
            urlpath(
                "batch-add/submit/",
                self.admin_site.admin_view(self.batch_add_submit_view),
                name="cases_caselog_batch_add_submit",
            ),
        ]
        return custom + urls

    def batch_add_view(self, request: HttpRequest) -> TemplateResponse:
        if not self.has_add_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        from apps.contracts.models import Contract

        contracts = (
            Contract.objects.filter(status="active", cases__isnull=False)
            .distinct()
            .order_by("name")
            .values_list("id", "name")
        )
        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("批量添加案件日志"),
                "opts": self.model._meta,
                "contracts": list(contracts),
                "batch_add_config": {
                    "casesUrl": reverse("admin:cases_caselog_batch_add_cases"),
                    "searchUrl": reverse("admin:cases_caselog_batch_add_search"),
                    "submitUrl": reverse("admin:cases_caselog_batch_add_submit"),
                    "changelistUrl": reverse("admin:cases_caselog_changelist"),
                    "caseDetailUrlTemplate": reverse("admin:cases_case_detail", args=[0]).replace("/0/", "/__ID__/"),
                },
            }
        )
        return TemplateResponse(request, "admin/cases/caselog/batch_add.html", context)

    def batch_add_cases_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_view_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        contract_id = payload.get("contract_id")
        if not contract_id:
            return JsonResponse({"success": False, "message": _("缺少 contract_id")}, status=400)

        from apps.cases.models import Case

        cases = (
            Case.objects.filter(contract_id=contract_id).order_by("name").values("id", "name", "status", "start_date")
        )
        case_list = []
        for c in cases:
            case_list.append(
                {
                    "id": c["id"],
                    "name": c["name"],
                    "status": c["status"],
                    "start_date": c["start_date"].isoformat() if c["start_date"] else None,
                }
            )
        return JsonResponse({"success": True, "cases": case_list})

    def batch_add_search_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_view_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        query = (payload.get("query") or "").strip()
        if not query:
            return JsonResponse({"success": False, "message": _("请输入搜索关键词")}, status=400)

        limit = min(int(payload.get("limit", 30)), 50)

        from apps.cases.models import Case
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder

        builder = CaseSearchQueryBuilder()
        qs = Case.objects.all()
        qs = builder.build_case_search_queryset(qs, query, status=None, limit=limit)
        cases = list(qs.values("id", "name", "status", "start_date"))
        case_list = [
            {
                "id": c["id"],
                "name": c["name"],
                "status": c["status"],
                "start_date": c["start_date"].isoformat() if c["start_date"] else None,
            }
            for c in cases
        ]
        return JsonResponse({"success": True, "cases": case_list})

    def batch_add_submit_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_add_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        case_ids = payload.get("case_ids")
        content = (payload.get("content") or "").strip()

        if not case_ids or not isinstance(case_ids, list):
            return JsonResponse({"success": False, "message": _("请至少选择一个案件")}, status=400)
        if not content:
            return JsonResponse({"success": False, "message": _("日志内容不能为空")}, status=400)

        user_id = getattr(request.user, "id", None)
        with transaction.atomic():
            logs = [CaseLog(case_id=case_id, content=content, actor_id=user_id or 0) for case_id in case_ids]
            created = CaseLog.objects.bulk_create(logs)

        return JsonResponse({"success": True, "created_count": len(created)})


@admin.register(CaseLogAttachment)
class CaseLogAttachmentAdmin(BaseModelAdmin):
    list_display = ("id", "log", "original_filename", "uploaded_at")
    search_fields = ("log__case__name", "original_filename")
    autocomplete_fields = ("log",)

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        """隐藏 Admin 首页入口，但保留直接 URL 访问能力"""
        return {}
