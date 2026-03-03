from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.oa_filing.models import OAConfig


class OAConfigForm(forms.ModelForm[OAConfig]):
    site_name = forms.ChoiceField(
        label=_("凭证站点名称"),
        help_text=_("从账号密码管理中已有的站点名称选择"),
    )

    class Meta:
        model = OAConfig
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from apps.organization.models import AccountCredential

        site_names: list[str] = list(
            AccountCredential.objects.values_list(
                "site_name",
                flat=True,
            )
            .distinct()
            .order_by("site_name")
        )
        choices: list[tuple[str, str]] = [("", "---------")]
        choices.extend((name, name) for name in site_names)
        self.fields["site_name"].choices = choices


@admin.register(OAConfig)
class OAConfigAdmin(admin.ModelAdmin[OAConfig]):
    form = OAConfigForm
    list_display: ClassVar = [
        "id",
        "site_name",
        "is_enabled",
        "updated_at",
    ]
    list_filter: ClassVar = ["is_enabled"]
    search_fields: ClassVar = ["site_name"]
    readonly_fields: ClassVar = ["created_at", "updated_at"]
    fieldsets: ClassVar = [
        (
            _("基本信息"),
            {"fields": ("site_name", "is_enabled")},
        ),
        (
            _("字段映射"),
            {"fields": ("field_mapping",)},
        ),
        (
            _("时间信息"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    ]
