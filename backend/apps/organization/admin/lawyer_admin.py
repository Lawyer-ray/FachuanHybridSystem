from __future__ import annotations

import logging
from typing import Any, ClassVar

import zipfile

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.admin.mixins import AdminImportExportMixin
from apps.organization.models import AccountCredential, Lawyer, LawFirm, Team

logger = logging.getLogger("apps.organization")


class LawyerAdminForm(forms.ModelForm[Lawyer]):
    class Meta:
        model = Lawyer
        fields = "__all__"

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        law_firm = cleaned.get("law_firm")
        lawyer_teams = cleaned.get("lawyer_teams")
        biz_teams = cleaned.get("biz_teams")
        if not lawyer_teams or lawyer_teams.count() == 0:
            raise ValidationError({"lawyer_teams": str(_("律师必须至少关联一个律师团队"))})
        if law_firm:
            bad_lt = [t for t in (lawyer_teams or []) if t.law_firm_id != law_firm.id]
            bad_bt = [t for t in (biz_teams or []) if t and t.law_firm_id != law_firm.id]
            if bad_lt or bad_bt:
                raise ValidationError(str(_("所选团队的所属律所必须与律师所属律所一致")))
        return cleaned


class AccountCredentialInlineForm(forms.ModelForm[AccountCredential]):
    class Meta:
        model = AccountCredential
        fields = "__all__"
        widgets: ClassVar[dict[str, Any]] = {"password": forms.PasswordInput(render_value=True)}


class AccountCredentialInline(admin.TabularInline[AccountCredential, AccountCredential]):
    model = AccountCredential
    form = AccountCredentialInlineForm
    extra = 1
    fields = ("site_name", "url", "account", "password")
    autocomplete_fields = ()


@admin.register(Lawyer)
class LawyerAdmin(AdminImportExportMixin, admin.ModelAdmin[Lawyer]):
    form = LawyerAdminForm
    list_display = ("id", "username", "real_name", "phone", "is_admin", "is_active")
    search_fields = ("username", "real_name", "phone")
    list_filter = ("is_admin", "is_active")
    filter_horizontal = ("lawyer_teams", "biz_teams")
    inlines: ClassVar[list[type[admin.TabularInline]]] = [AccountCredentialInline]  # type: ignore[type-arg]
    export_model_name = "lawyer"
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]

    def serialize_queryset(self, queryset: Any) -> list[dict[str, Any]]:
        result = []
        for obj in queryset.prefetch_related("lawyer_teams", "biz_teams", "credentials"):
            result.append({
                "username": obj.username,
                "real_name": obj.real_name,
                "phone": obj.phone or "",
                "license_no": obj.license_no,
                "id_card": obj.id_card,
                "is_admin": obj.is_admin,
                "is_active": obj.is_active,
                "law_firm": obj.law_firm.name if obj.law_firm else None,
                "lawyer_teams": [t.name for t in obj.lawyer_teams.all()],
                "biz_teams": [t.name for t in obj.biz_teams.all()],
                "credentials": [
                    {"site_name": c.site_name, "url": c.url or "", "account": c.account, "password": c.password}
                    for c in obj.credentials.all()
                ],
            })
        return result

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: zipfile.ZipFile | None
    ) -> tuple[int, int, list[str]]:
        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            username = item.get("username", "")
            try:
                if Lawyer.objects.filter(username=username).exists():
                    skipped += 1
                    continue
                law_firm = None
                if item.get("law_firm"):
                    law_firm = LawFirm.objects.filter(name=item["law_firm"]).first()

                lawyer = Lawyer.objects.create_user(
                    username=username,
                    password=Lawyer.objects.make_random_password(),
                    real_name=item.get("real_name", ""),
                    phone=item.get("phone") or None,
                    license_no=item.get("license_no", ""),
                    id_card=item.get("id_card", ""),
                    is_admin=item.get("is_admin", False),
                    is_active=item.get("is_active", False),
                    is_staff=item.get("is_admin", False),
                    law_firm=law_firm,
                )
                if item.get("lawyer_teams"):
                    teams = Team.objects.filter(name__in=item["lawyer_teams"])
                    lawyer.lawyer_teams.set(teams)
                if item.get("biz_teams"):
                    teams = Team.objects.filter(name__in=item["biz_teams"])
                    lawyer.biz_teams.set(teams)
                for cred in item.get("credentials", []):
                    AccountCredential.objects.create(
                        lawyer=lawyer,
                        site_name=cred.get("site_name", ""),
                        url=cred.get("url", ""),
                        account=cred.get("account", ""),
                        password=cred.get("password", ""),
                    )
                success += 1
            except Exception as exc:
                logger.exception("导入律师失败", extra={"index": i, "username": username})
                errors.append(f"[{i}] {username} ({type(exc).__name__}): {exc}")
        return success, skipped, errors
