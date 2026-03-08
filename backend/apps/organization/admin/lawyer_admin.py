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
from apps.organization.models.team import TeamType

logger = logging.getLogger("apps.organization")


class LawyerAdminForm(forms.ModelForm[Lawyer]):
    new_password = forms.CharField(
        required=False,
        label=_("新密码"),
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("留空则不修改密码"),
    )
    lawyer_team = forms.ModelChoiceField(
        queryset=Team.objects.filter(team_type=TeamType.LAWYER),
        required=False,
        label=_("律师团队"),
    )
    biz_team = forms.ModelChoiceField(
        queryset=Team.objects.filter(team_type=TeamType.BIZ),
        required=False,
        label=_("业务团队"),
    )

    class Meta:
        model = Lawyer
        fields = ("username", "password", "real_name", "phone", "license_no", "id_card", "license_pdf", "is_active", "is_admin", "is_staff", "is_superuser")
        widgets: ClassVar[dict[str, Any]] = {
            "password": forms.TextInput(attrs={"readonly": True, "style": "color:#999;background:#f5f5f5;"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lt = self.instance.lawyer_teams.first()
            bt = self.instance.biz_teams.first()
            self.fields["lawyer_team"].initial = lt
            self.fields["biz_team"].initial = bt

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        if not cleaned.get("lawyer_team"):
            raise ValidationError({"lawyer_team": str(_("律师必须至少关联一个律师团队"))})
        return cleaned

    def save(self, commit: bool = True) -> Lawyer:
        user = super().save(commit=False)
        new_password = self.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)
        lt = self.cleaned_data.get("lawyer_team")
        bt = self.cleaned_data.get("biz_team")
        if lt and lt.law_firm:
            user.law_firm = lt.law_firm
        if commit:
            user.save()
            user.lawyer_teams.set([lt] if lt else [])
            user.biz_teams.set([bt] if bt else [])
        # 存起来供 save_related 用（save_m2m 会清空，需要再设一次）
        self._pending_lawyer_team = lt
        self._pending_biz_team = bt
        return user


class AccountCredentialInlineForm(forms.ModelForm[AccountCredential]):
    class Meta:
        model = AccountCredential
        fields = "__all__"
        widgets: ClassVar[dict[str, Any]] = {
            "password": forms.PasswordInput(render_value=True),
            "url": forms.TextInput(attrs={"class": "vTextField"}),
        }


class AccountCredentialInline(admin.TabularInline[AccountCredential, AccountCredential]):
    model = AccountCredential
    form = AccountCredentialInlineForm
    extra = 1
    fields = ("site_name", "url", "account", "password")
    autocomplete_fields = ()
    show_change_link = False
    verbose_name = _("账号密码")
    verbose_name_plural = _("账号密码")

    def get_extra(self, request: Any, obj: Any = None, **kwargs: Any) -> int:
        return 1 if not obj or not obj.credentials.exists() else 0


@admin.register(Lawyer)
class LawyerAdmin(AdminImportExportMixin, admin.ModelAdmin[Lawyer]):
    form = LawyerAdminForm
    list_display = ("id", "username", "real_name", "phone", "is_admin", "is_active")
    search_fields = ("username", "real_name", "phone")
    list_filter = ("is_admin", "is_active")
    inlines: ClassVar[list[type[admin.TabularInline]]] = [AccountCredentialInline]  # type: ignore[type-arg]
    export_model_name = "lawyer"
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]
    fieldsets: ClassVar = (
        (_("账号信息"), {"fields": ("username", "password", "new_password")}),
        (_("个人信息"), {"fields": ("real_name", "phone", "license_no", "id_card", "license_pdf")}),
        (_("组织关系"), {"fields": ("lawyer_team", "biz_team")}),
        (_("权限"), {"fields": ("is_active", "is_admin", "is_staff", "is_superuser")}),
    )

    class Media:
        css = {"all": ("admin/css/lawyer_admin.css",)}

    def save_related(self, request: Any, form: Any, formsets: Any, change: Any) -> None:
        super().save_related(request, form, formsets, change)
        # save_m2m() 会清空未在 Meta.fields 里的 M2M，在此之后重新设置
        obj = form.instance
        lt = getattr(form, "_pending_lawyer_team", None)
        bt = getattr(form, "_pending_biz_team", None)
        obj.lawyer_teams.set([lt] if lt else [])
        obj.biz_teams.set([bt] if bt else [])

    def get_file_paths(self, queryset: Any) -> list[str]:
        return [
            str(obj.license_pdf)
            for obj in queryset
            if obj.license_pdf
        ]

    def serialize_queryset(self, queryset: Any) -> list[dict[str, Any]]:
        result = []
        for obj in queryset.prefetch_related("lawyer_teams", "biz_teams", "credentials"):
            result.append({
                "username": obj.username,
                "real_name": obj.real_name,
                "phone": obj.phone or "",
                "license_no": obj.license_no,
                "id_card": obj.id_card,
                "license_pdf": str(obj.license_pdf) if obj.license_pdf else "",
                "password": "",  # 导入时填写明文密码，留空则随机生成
                "is_admin": obj.is_admin,
                "is_active": obj.is_active,
                "law_firm": obj.law_firm.name if obj.law_firm else None,
                "lawyer_teams": [
                    {"name": t.name, "law_firm": t.law_firm.name if t.law_firm else None}
                    for t in obj.lawyer_teams.all()
                ],
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
        import secrets

        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            username = item.get("username", "")
            try:
                existing = Lawyer.objects.filter(username=username).first()
                if existing:
                    update_fields: list[str] = []
                    for field, json_key in [
                        ("real_name", "real_name"),
                        ("phone", "phone"),
                        ("license_no", "license_no"),
                        ("id_card", "id_card"),
                    ]:
                        if not getattr(existing, field) and item.get(json_key):
                            setattr(existing, field, item[json_key])
                            update_fields.append(field)
                    if not existing.license_pdf and item.get("license_pdf"):
                        existing.license_pdf = item["license_pdf"]
                        update_fields.append("license_pdf")
                    if not existing.law_firm and item.get("law_firm"):
                        existing.law_firm, _ = LawFirm.objects.get_or_create(name=item["law_firm"])
                        update_fields.append("law_firm")
                    if update_fields:
                        existing.save(update_fields=update_fields)

                    # lawyer_teams：只补充不存在的
                    if item.get("lawyer_teams"):
                        existing_lt_names = set(existing.lawyer_teams.values_list("name", flat=True))
                        for t in item["lawyer_teams"]:
                            t_name = t if isinstance(t, str) else t.get("name", "")
                            if t_name not in existing_lt_names:
                                t_firm_name = None if isinstance(t, str) else t.get("law_firm")
                                t_firm = LawFirm.objects.get_or_create(name=t_firm_name)[0] if t_firm_name else existing.law_firm
                                team, _ = Team.objects.get_or_create(name=t_name, team_type=TeamType.LAWYER, defaults={"law_firm": t_firm})
                                existing.lawyer_teams.add(team)

                    # biz_teams：只补充不存在的
                    if item.get("biz_teams"):
                        existing_bt_names = set(existing.biz_teams.values_list("name", flat=True))
                        for t_name in item["biz_teams"]:
                            if t_name not in existing_bt_names:
                                team, _ = Team.objects.get_or_create(name=t_name, team_type=TeamType.BIZ, defaults={"law_firm": existing.law_firm})
                                existing.biz_teams.add(team)

                    # credentials：只补充 site_name 不存在的
                    if item.get("credentials"):
                        existing_sites = set(existing.credentials.values_list("site_name", flat=True))
                        for cred in item["credentials"]:
                            if cred.get("site_name") not in existing_sites:
                                AccountCredential.objects.create(
                                    lawyer=existing,
                                    site_name=cred.get("site_name", ""),
                                    url=cred.get("url", ""),
                                    account=cred.get("account", ""),
                                    password=cred.get("password", ""),
                                )

                    success += 1
                    continue

                # 自动创建律所
                law_firm: LawFirm | None = None
                if item.get("law_firm"):
                    law_firm, _ = LawFirm.objects.get_or_create(name=item["law_firm"])

                password = item.get("password") or secrets.token_urlsafe(16)
                lawyer = Lawyer.objects.create_user(
                    username=username,
                    password=password,
                    real_name=item.get("real_name", ""),
                    phone=item.get("phone") or None,
                    license_no=item.get("license_no", ""),
                    id_card=item.get("id_card", ""),
                    is_admin=item.get("is_admin", False),
                    is_active=item.get("is_active", False),
                    is_staff=item.get("is_admin", False),
                    law_firm=law_firm,
                )

                # license_pdf：文件已由 _extract_files 还原到 MEDIA_ROOT，直接赋相对路径
                if item.get("license_pdf"):
                    lawyer.license_pdf = item["license_pdf"]
                    lawyer.save(update_fields=["license_pdf"])

                # 自动创建律师团队（含律所关联）
                if item.get("lawyer_teams"):
                    lawyer_team_objs: list[Team] = []
                    for t in item["lawyer_teams"]:
                        t_name = t if isinstance(t, str) else t.get("name", "")
                        t_firm_name = None if isinstance(t, str) else t.get("law_firm")
                        t_firm = LawFirm.objects.get_or_create(name=t_firm_name)[0] if t_firm_name else law_firm
                        team, _ = Team.objects.get_or_create(
                            name=t_name,
                            team_type=TeamType.LAWYER,
                            defaults={"law_firm": t_firm},
                        )
                        lawyer_team_objs.append(team)
                    lawyer.lawyer_teams.set(lawyer_team_objs)

                # 自动创建业务团队
                if item.get("biz_teams"):
                    biz_team_objs: list[Team] = []
                    for t_name in item["biz_teams"]:
                        team, _ = Team.objects.get_or_create(
                            name=t_name,
                            team_type=TeamType.BIZ,
                            defaults={"law_firm": law_firm},
                        )
                        biz_team_objs.append(team)
                    lawyer.biz_teams.set(biz_team_objs)

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
