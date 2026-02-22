"""Django admin configuration."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.reminders.models import Reminder


class ReminderAdminForm(forms.ModelForm[Reminder]):
    class Meta:
        model = Reminder
        fields: str = "__all__"
        help_texts: ClassVar[dict[str, Any]] = {
            "metadata": _(
                '用于存放"结构化扩展信息"的 JSON(不参与业务必填).可留空或填 {}.'
                "常见键:source(来源,如 court_sms / manual)、file_name(来源文件名)、"
                'external_id(外部ID)、note(备注).示例:{"source":"court_sms","file_name":"传票.pdf"}'
            ),
        }
        widgets: ClassVar[dict[str, Any]] = {
            "metadata": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_metadata(self) -> Any:
        value = self.cleaned_data.get("metadata")
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                raise forms.ValidationError(_("请输入合法的 JSON 格式")) from None
            if not isinstance(parsed, dict):
                raise forms.ValidationError(_("请输入合法的 JSON 对象（非数组或标量）"))
            return parsed
        raise forms.ValidationError(_("请输入合法的 JSON 格式"))


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin[Reminder]):
    form = ReminderAdminForm
    list_display = (
        "id",
        "due_at",
        "reminder_type",
        "content",
        "contract",
        "case_log",
        "created_at",
    )
    list_display_links = ("id", "content")
    list_filter = ("reminder_type", "due_at", "created_at")
    search_fields = ("content",)
    list_select_related = ("contract", "case_log")
    autocomplete_fields: ClassVar[list[str]] = ["contract", "case_log"]
    readonly_fields: ClassVar[tuple[str, ...]] = ("created_at", "updated_at")
    ordering = ("-due_at", "-id")
    list_per_page = 30
