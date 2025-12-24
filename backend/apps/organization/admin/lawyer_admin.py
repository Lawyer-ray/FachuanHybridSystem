from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from ..models import Lawyer, AccountCredential

class LawyerAdminForm(forms.ModelForm):
    class Meta:
        model = Lawyer
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        law_firm = cleaned.get("law_firm")
        lawyer_teams = cleaned.get("lawyer_teams")
        biz_teams = cleaned.get("biz_teams")
        if not lawyer_teams or lawyer_teams.count() == 0:
            raise ValidationError({"lawyer_teams": "律师必须至少关联一个律师团队"})
        if law_firm:
            bad_lt = [t for t in (lawyer_teams or []) if t.law_firm_id != law_firm.id]
            bad_bt = [t for t in (biz_teams or []) if t and t.law_firm_id != law_firm.id]
            if bad_lt or bad_bt:
                raise ValidationError("所选团队的所属律所必须与律师所属律所一致")
        return cleaned


class AccountCredentialInlineForm(forms.ModelForm):
    class Meta:
        model = AccountCredential
        fields = "__all__"
        widgets = {
            "password": forms.PasswordInput(render_value=True)
        }


class AccountCredentialInline(admin.TabularInline):
    model = AccountCredential
    form = AccountCredentialInlineForm
    extra = 1
    fields = ("site_name", "url", "account", "password")
    autocomplete_fields = ()


@admin.register(Lawyer)
class LawyerAdmin(admin.ModelAdmin):
    form = LawyerAdminForm
    list_display = ("id", "username", "real_name", "phone", "is_admin", "is_active")
    search_fields = ("username", "real_name", "phone")
    list_filter = ("is_admin", "is_active")
    filter_horizontal = ("lawyer_teams", "biz_teams")
    inlines = [AccountCredentialInline]
