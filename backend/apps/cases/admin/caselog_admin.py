from __future__ import annotations

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from apps.cases.admin.base_admin import BaseModelAdmin, BaseTabularInline
from apps.cases.models import CaseLog, CaseLogAttachment


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    extra = 0
    readonly_fields = ("uploaded_at",)
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
    list_filter = ("created_at",)
    search_fields = ("content", "case__name")
    ordering = ("-created_at",)
    autocomplete_fields = ("case", "actor")
    exclude = ("actor", "source_subfolder")
    inlines = (ReminderInline, CaseLogAttachmentInline)
    change_form_template = "admin/cases/caselog/change_form.html"

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


@admin.register(CaseLogAttachment)
class CaseLogAttachmentAdmin(BaseModelAdmin):
    list_display = ("id", "log", "uploaded_at")
    search_fields = ("log__case__name",)
    autocomplete_fields = ("log",)

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        """隐藏 Admin 首页入口，但保留直接 URL 访问能力"""
        return {}
