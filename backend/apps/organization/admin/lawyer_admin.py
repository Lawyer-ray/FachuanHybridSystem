from __future__ import annotations

import zipfile
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.core.admin.mixins import AdminImportExportMixin
from apps.organization.models import AccountCredential, Lawyer, Team
from apps.organization.models.team import TeamType
from apps.organization.services.lawyer_import_service import LawyerImportService
from apps.social_auth.models import SocialAccount


def _get_lawyer_import_service() -> LawyerImportService:
    return LawyerImportService()


def _invalidate_lawyer_teams_access(lawyer: Lawyer, affected_team_ids: set[int]) -> None:  # pragma: no cover
    """律师团队/业务团队变更后，刷新受影响用户的组织可见范围缓存。

    对照 LawyerMutationService._set_lawyer_teams 末尾的失效调用：
    后台表单直接 lawyer_teams.set() 绕过了 mutation 服务，需在此补失效。
    """
    from apps.core.infrastructure import invalidate_users_access_context

    affected_user_ids = set(
        Lawyer.objects.filter(lawyer_teams__id__in=affected_team_ids).values_list("id", flat=True).distinct()
    )
    affected_user_ids |= set(
        Lawyer.objects.filter(biz_teams__id__in=affected_team_ids).values_list("id", flat=True).distinct()
    )
    affected_user_ids.add(lawyer.pk)
    invalidate_users_access_context(list(affected_user_ids), org_access=True, case_grants=False)


class LawyerAdminForm(forms.ModelForm[Lawyer]):  # pragma: no cover
    new_password = forms.CharField(
        required=False,
        label="新密码",
        # Keep password entry masked to avoid accidental plain text exposure in admin.
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="留空则不修改密码",
    )
    lawyer_team = forms.ModelChoiceField(
        queryset=Team.objects.filter(team_type=TeamType.LAWYER),
        required=False,
        label="律师团队",
    )
    biz_team = forms.ModelChoiceField(
        queryset=Team.objects.filter(team_type=TeamType.BIZ),
        required=False,
        label="业务团队",
    )

    class Meta:  # pragma: no cover
        model = Lawyer
        fields = (
            "username",
            "password",
            "real_name",
            "phone",
            "avatar",
            "license_no",
            "id_card",
            "license_pdf",
            "is_active",
            "is_admin",
            "is_staff",
            "is_superuser",
        )
        widgets: ClassVar[dict[str, Any]] = {
            # Existing password value remains read-only; do not turn this back into editable plain text.
            "password": forms.TextInput(attrs={"readonly": True, "style": "color:#999;background:#f5f5f5;"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lt = self.instance.lawyer_teams.first()
            bt = self.instance.biz_teams.first()
            self.fields["lawyer_team"].initial = lt
            self.fields["biz_team"].initial = bt

    def clean(self) -> dict[str, Any]:  # pragma: no cover
        cleaned: dict[str, Any] = super().clean() or {}
        if not cleaned.get("lawyer_team"):
            raise ValidationError({"lawyer_team": "律师必须至少关联一个律师团队"})
        return cleaned

    def save(self, commit: bool = True) -> Lawyer:  # pragma: no cover
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
            # 先记旧团队 id，供 save_related 统计受影响用户后失效访问缓存
            self._old_lawyer_team_ids = set(user.lawyer_teams.values_list("id", flat=True))
            self._old_biz_team_ids = set(user.biz_teams.values_list("id", flat=True))
            user.lawyer_teams.set([lt] if lt else [])
            user.biz_teams.set([bt] if bt else [])
        # 存起来供 save_related 用（save_m2m 会清空，需要再设一次）
        self._pending_lawyer_team = lt
        self._pending_biz_team = bt
        return user


class AccountCredentialInlineForm(forms.ModelForm[AccountCredential]):  # pragma: no cover
    class Meta:  # pragma: no cover
        model = AccountCredential
        fields = "__all__"
        widgets: ClassVar[dict[str, Any]] = {
            # 安全审计 B-17：不回填明文（render_value=False），空值=不修改
            "password": forms.PasswordInput(render_value=False),
            "url": forms.TextInput(attrs={"class": "vTextField"}),
        }

    def clean_password(self) -> str:  # pragma: no cover
        value = self.cleaned_data.get("password") or ""
        if not value.strip() and self.instance and self.instance.pk:
            # 安全审计 B-17：编辑行留空 → 保留原密码，避免被空串覆盖
            return str(self.instance.password)
        return value


class AccountCredentialInline(admin.TabularInline[AccountCredential, AccountCredential]):  # pragma: no cover
    model = AccountCredential
    form = AccountCredentialInlineForm
    extra = 1
    fields = ("site_name", "url", "account", "password")
    autocomplete_fields = ()
    show_change_link = False
    verbose_name = "账号密码"
    verbose_name_plural = "账号密码"

    def get_extra(self, request: Any, obj: Any = None, **kwargs: Any) -> int:  # pragma: no cover
        return 1 if not obj or not obj.credentials.exists() else 0


class SocialAccountInline(admin.TabularInline[SocialAccount, SocialAccount]):  # pragma: no cover
    """只读展示扫码登录绑定，用于确认「这个飞书身份是哪位律师」。

    只读是刻意的：绑定关系只能由律师本人在「个人设置 → 账号绑定」扫码产生，
    后台编辑会造出指向错误律师的记录。需要解绑换号时走社交账号后台。
    """

    model = SocialAccount
    extra = 0
    can_delete = False
    fields = ("provider", "display_name", "provider_uid", "avatar_url", "created_at")
    readonly_fields = fields
    verbose_name = "社交账号"
    verbose_name_plural = "社交账号（扫码登录绑定）"

    def has_add_permission(self, request: Any, obj: Any = None) -> bool:
        return False


class SocialLoginFilter(admin.SimpleListFilter):  # pragma: no cover
    """按「是否绑定了扫码登录」筛律师，快速找出还没绑定的账号。"""

    title = "登录方式"
    parameter_name = "social_login"

    def lookups(self, request: Any, model_admin: Any) -> list[tuple[str, str]]:
        return [("yes", "已绑定扫码登录"), ("no", "仅账密登录")]

    def queryset(self, request: Any, queryset: Any) -> Any:
        if self.value() == "yes":
            return queryset.filter(social_accounts__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(social_accounts__isnull=True)
        return queryset


@admin.register(Lawyer)
class LawyerAdmin(AdminImportExportMixin, admin.ModelAdmin):  # pragma: no cover
    form = LawyerAdminForm
    list_display = ("id", "username", "real_name", "phone", "is_admin", "is_active", "social_bindings")
    search_fields = ("username", "real_name", "phone")
    list_filter = ("is_admin", "is_active", SocialLoginFilter)
    inlines: ClassVar[list[type[admin.TabularInline]]] = [AccountCredentialInline, SocialAccountInline]  # type: ignore[assignment]
    export_model_name = "lawyer"
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]  # type: ignore[misc]
    fieldsets: ClassVar = (
        ("账号信息", {"fields": ("username", "password", "new_password")}),
        ("个人信息", {"fields": ("real_name", "phone", "avatar", "license_no", "id_card", "license_pdf")}),
        ("组织关系", {"fields": ("lawyer_team", "biz_team")}),
        ("权限", {"fields": ("is_active", "is_admin", "is_staff", "is_superuser")}),
    )

    class Media:  # pragma: no cover
        css = {"all": ("admin/css/lawyer_admin.css",)}

    def save_related(self, request: Any, form: Any, formsets: Any, change: Any) -> None:  # pragma: no cover
        super().save_related(request, form, formsets, change)
        # save_m2m() 会清空未在 Meta.fields 里的 M2M，在此之后重新设置
        obj = form.instance
        lt = getattr(form, "_pending_lawyer_team", None)
        bt = getattr(form, "_pending_biz_team", None)
        obj.lawyer_teams.set([lt] if lt else [])
        obj.biz_teams.set([bt] if bt else [])
        # 团队变更（新旧团队成员 + 本人）需失效组织可见范围缓存
        old_team_ids = getattr(form, "_old_lawyer_team_ids", set()) | getattr(form, "_old_biz_team_ids", set())
        new_team_ids = {t.id for t in (lt, bt) if t is not None}
        _invalidate_lawyer_teams_access(obj, old_team_ids | new_team_ids)

    def get_queryset(self, request: Any) -> Any:
        # 列表页要显示 social_bindings 一列，预先取回绑定关系避免 N+1
        return super().get_queryset(request).prefetch_related("social_accounts")

    @admin.display(description="扫码登录绑定")
    def social_bindings(self, obj: Lawyer) -> str:
        accounts = list(obj.social_accounts.all())
        if not accounts:
            return "—"
        return "、".join(f"{a.provider}:{a.display_name or a.provider_uid[:10]}" for a in accounts)

    def get_file_paths(self, queryset: Any) -> list[str]:  # pragma: no cover
        return [str(obj.license_pdf) for obj in queryset if obj.license_pdf]

    def serialize_queryset(self, queryset: Any) -> list[dict[str, Any]]:  # pragma: no cover
        result = []
        for obj in queryset.prefetch_related("lawyer_teams", "biz_teams", "credentials"):
            result.append(
                {
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
                        # 安全审计 B-16：导出不再包含明文密码（导入端支持留空随机生成）
                        {"site_name": c.site_name, "url": c.url or "", "account": c.account, "password": ""}
                        for c in obj.credentials.all()
                    ],
                }
            )
        return result

    def handle_json_import(  # pragma: no cover
        self, data_list: list[dict[str, Any]], user: str, zip_file: zipfile.ZipFile | None
    ) -> tuple[int, int, list[str]]:
        del zip_file  # kept for AdminImportExportMixin compatibility
        # Keep admin thin: import behavior lives in LawyerImportService, preserving existing business rules.
        return _get_lawyer_import_service().import_from_json(data_list, actor=user)
