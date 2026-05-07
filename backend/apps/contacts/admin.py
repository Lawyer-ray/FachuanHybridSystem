from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.contacts.models import CaseContact

if TYPE_CHECKING:
    from typing import TypeAlias

    BaseTabularInline: TypeAlias = admin.TabularInline[Any, Any]
    BaseModelAdmin: TypeAlias = admin.ModelAdmin[Any]
else:
    try:
        import nested_admin

        BaseTabularInline = nested_admin.NestedTabularInline
        BaseModelAdmin = nested_admin.NestedModelAdmin
    except ImportError:
        BaseTabularInline = admin.TabularInline
        BaseModelAdmin = admin.ModelAdmin


class CaseContactAdminForm(forms.ModelForm[CaseContact]):
    """案件联系人表单 - 主管机关支持自动补全"""

    authority_name = forms.CharField(
        label=_("主管机关"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "vTextField js-court-autocomplete",
                "placeholder": _("请输入法院/机关名称..."),
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = CaseContact
        fields = "__all__"
        exclude = ("authority",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.authority:
            self.fields["authority_name"].initial = self.instance.authority.name

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        authority_name = cleaned.pop("authority_name", "").strip()
        if authority_name:
            from apps.cases.models import SupervisingAuthority

            authority, _created = SupervisingAuthority.objects.get_or_create(
                case=self.instance.case,
                name=authority_name,
                defaults={"authority_type": "court"},
            )
            self.instance.authority = authority
        else:
            self.instance.authority = None
        return cleaned


class CaseContactInlineForm(forms.ModelForm[CaseContact]):
    """案件联系人内联表单 - 主管机关支持自动补全"""

    authority_name = forms.CharField(
        label=_("主管机关"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "vTextField js-court-autocomplete",
                "placeholder": _("搜索法院/机关名称..."),
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = CaseContact
        fields = "__all__"
        exclude = ("authority",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.authority:
            self.fields["authority_name"].initial = self.instance.authority.name

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        authority_name = cleaned.pop("authority_name", "").strip()
        if authority_name:
            from apps.cases.models import SupervisingAuthority

            authority, _created = SupervisingAuthority.objects.get_or_create(
                case=self.instance.case,
                name=authority_name,
                defaults={"authority_type": "court"},
            )
            self.instance.authority = authority
        else:
            self.instance.authority = None
        return cleaned


class CaseContactInline(BaseTabularInline):
    model = CaseContact
    form = CaseContactInlineForm
    extra = 1
    fields = ("name", "role", "phone", "stage", "authority_name", "note")


@admin.register(CaseContact)
class CaseContactAdmin(BaseModelAdmin):
    form = CaseContactAdminForm
    list_display = ("id", "case", "name", "role", "phone", "stage", "authority")
    list_filter = ("role", "stage")
    search_fields = ("name", "phone", "case__name")
    autocomplete_fields = ("case",)

    class Media:
        js = (
            "cases/js/autocomplete.js",
            "cases/js/autocomplete_init.js",
        )
