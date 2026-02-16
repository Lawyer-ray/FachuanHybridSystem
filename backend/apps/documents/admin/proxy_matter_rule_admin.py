"""Django admin configuration."""

from typing import Any

from django import forms
from django.contrib import admin

from apps.core.enums import LegalStatus
from apps.documents.models import ProxyMatterRule


class ProxyMatterRuleAdminForm(forms.ModelForm):
    legal_statuses = forms.MultipleChoiceField(
        label="我方诉讼地位",
        choices=LegalStatus.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="可单选或多选;不选表示匹配任意诉讼地位",
    )

    class Meta:
        model = ProxyMatterRule
        fields: str = "__all__"


@admin.register(ProxyMatterRule)
class ProxyMatterRuleAdmin(admin.ModelAdmin):
    form = ProxyMatterRuleAdminForm
    list_display: tuple[Any, ...] = (
        "id",
        "case_type",
        "case_stage",
        "legal_statuses_display",
        "legal_status_match_mode",
        "priority",
        "is_active",
        "updated_at",
    )
    list_filter: tuple[Any, ...] = (
        "is_active",
        "case_type",
        "case_stage",
        "legal_status_match_mode",
    )
    search_fields: tuple[Any, ...] = ("items_text",)
    ordering: tuple[Any, ...] = ("-is_active", "priority", "id")

    def legal_statuses_display(self, obj: ProxyMatterRule) -> str:
        return obj.get_legal_statuses_display() or "任意"

    legal_statuses_display.short_description = "我方诉讼地位"
