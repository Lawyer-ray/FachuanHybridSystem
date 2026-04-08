"""Django admin configuration."""

from __future__ import annotations

import logging
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models.enums import LegalStatus, SimpleCaseType
from apps.documents.models import ProxyMatterRule
from apps.documents.services.proxy_matter_rule_init_service import ProxyMatterRuleInitService

logger = logging.getLogger(__name__)


def _get_proxy_matter_rule_init_service() -> ProxyMatterRuleInitService:
    return ProxyMatterRuleInitService()


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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
    change_list_template = "admin/documents/proxymatterrule/change_list.html"

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

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom_urls = [
            path(
                "initialize-defaults/",
                self.admin_site.admin_view(self.initialize_defaults_view),
                name="documents_proxymatterrule_initialize",
            )
        ]
        return custom_urls + urls

    def initialize_defaults_view(self, request: Any) -> HttpResponseRedirect:
        try:
            result = _get_proxy_matter_rule_init_service().initialize_defaults()
        except Exception as exc:
            logger.exception("初始化代理事项规则失败")
            messages.error(request, _("初始化失败：%(error)s") % {"error": str(exc)})
            return HttpResponseRedirect(reverse("admin:documents_proxymatterrule_changelist"))

        created = int(result.get("created", 0))
        updated = int(result.get("updated", 0))

        if created > 0 or updated > 0:
            messages.success(
                request,
                _("初始化完成：新增 %(created)d 条，更新 %(updated)d 条") % {"created": created, "updated": updated},
            )
        else:
            messages.info(request, _("初始化完成：所有初始化数据已存在，无需变更"))

        return HttpResponseRedirect(reverse("admin:documents_proxymatterrule_changelist"))

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:
        extra_context = extra_context or {}
        extra_context["initialize_url"] = reverse("admin:documents_proxymatterrule_initialize")
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description=_("案件类型"))
    def case_types_display(self, obj: ProxyMatterRule) -> str:
        return obj.get_case_types_display() or "任意"

    @admin.display(description=_("我方诉讼地位"))
    def legal_statuses_display(self, obj: ProxyMatterRule) -> str:
        return obj.get_legal_statuses_display() or "任意"
