"""Django admin configuration."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.core.enums import LegalStatus, SimpleCaseType
from apps.documents.models import ProxyMatterRule


class ProxyMatterRuleAdminForm(forms.ModelForm[ProxyMatterRule]):
    case_types_field = forms.MultipleChoiceField(
        label="案件类型",
        choices=SimpleCaseType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="可单选或多选;不选表示匹配任意案件类型",
    )
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            selected = list(self.instance.case_types or [])
            if not selected and self.instance.case_type:
                selected = [self.instance.case_type]
            self.fields["case_types_field"].initial = selected

    def save(self, commit: bool = True) -> ProxyMatterRule:
        instance = super().save(commit=False)
        selected = [str(x) for x in self.cleaned_data.get("case_types_field", []) if x]
        instance.case_types = selected
        # 兼容历史逻辑: 同步一个主值到旧字段
        instance.case_type = selected[0] if selected else None
        if commit:
            instance.save()
        return instance


@admin.register(ProxyMatterRule)
class ProxyMatterRuleAdmin(admin.ModelAdmin[ProxyMatterRule]):
    form = ProxyMatterRuleAdminForm
    list_display = (
        "id",
        "case_types_display",
        "case_stage",
        "legal_statuses_display",
        "legal_status_match_mode",
        "priority",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "case_stage",
        "legal_status_match_mode",
    )
    fields = (
        "case_types_field",
        "case_stage",
        "legal_statuses",
        "legal_status_match_mode",
        "items_text",
        "priority",
        "is_active",
    )
    search_fields = ("items_text",)
    ordering = ("-is_active", "priority", "id")

    @admin.display(description=_("案件类型"))
    def case_types_display(self, obj: ProxyMatterRule) -> str:
        return obj.get_case_types_display() or "任意"

    @admin.display(description=_("我方诉讼地位"))
    def legal_statuses_display(self, obj: ProxyMatterRule) -> str:
        return obj.get_legal_statuses_display() or "任意"
