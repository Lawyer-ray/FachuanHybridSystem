from __future__ import annotations

from django import forms
from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base_admin import BaseModelAdmin, BaseTabularInline
from apps.cases.models import (
    CaseLog,
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialSide,
    CaseMaterialType,
    CaseParty,
    SupervisingAuthority,
)
from apps.cases.services.material.wiring import build_case_material_service


OTHER_MATERIAL_TYPE_NAME = "其它材料"
DEFAULT_PARTY_MATERIAL_TYPE_ORDER = (
    "起诉状",
    "答辩状",
    "证据材料",
    "身份材料",
    "授权委托材料",
    "保全材料",
    "执行材料",
    OTHER_MATERIAL_TYPE_NAME,
)
DEFAULT_NON_PARTY_MATERIAL_TYPE_ORDER = (
    "法院文书",
    "送达材料",
    "回执材料",
    "裁定/决定文书",
    OTHER_MATERIAL_TYPE_NAME,
)
DEFAULT_MATERIAL_TYPE_ORDER = {
    CaseMaterialCategory.PARTY: {name: idx for idx, name in enumerate(DEFAULT_PARTY_MATERIAL_TYPE_ORDER)},
    CaseMaterialCategory.NON_PARTY: {name: idx for idx, name in enumerate(DEFAULT_NON_PARTY_MATERIAL_TYPE_ORDER)},
}


class CaseLogAttachmentInlineForm(forms.ModelForm[CaseLogAttachment]):
    file = forms.FileField(
        required=False,
        label=_("上传文件"),
        help_text=_("留空表示不替换现有文件。"),
    )
    target_subdir = forms.CharField(
        required=False,
        label=_("保存子目录"),
        help_text=_("文件会先归属到案件业务文件夹，再保存到这里填写的子目录；留空时系统会自动推荐。"),
    )
    sync_to_case_material = forms.BooleanField(
        required=False,
        label=_("同步到案件材料"),
        help_text=_("勾选后，该附件会在案件详情的我方当事人材料、对方当事人材料或非当事人材料中展示。"),
    )
    material_category = forms.ChoiceField(
        required=False,
        label=_("材料位置"),
        choices=(("", _("请选择")),) + tuple(CaseMaterialCategory.choices),
        widget=forms.HiddenInput,
    )
    material_side = forms.ChoiceField(
        required=False,
        label=_("当事人方向"),
        choices=(("", _("请选择")),) + tuple(CaseMaterialSide.choices),
        widget=forms.HiddenInput,
    )
    material_parties = forms.CharField(
        required=False,
        label=_("关联当事人"),
        help_text=_("可选；用于在材料列表中显示具体当事人。"),
        widget=forms.HiddenInput,
    )
    material_supervising_authority = forms.CharField(
        required=False,
        label=_("主管机关"),
        widget=forms.HiddenInput,
    )
    material_type = forms.CharField(
        required=False,
        label=_("材料类型"),
        widget=forms.HiddenInput,
    )
    material_type_name = forms.CharField(
        required=False,
        label=_("自定义材料类型"),
        help_text=_("未选择已有类型时填写。"),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = CaseLogAttachment
        fields = (
            "file",
            "target_subdir",
            "sync_to_case_material",
            "material_category",
            "material_side",
            "material_parties",
            "material_supervising_authority",
            "material_type",
            "material_type_name",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.subdir_path:
            self.fields["target_subdir"].initial = self.instance.subdir_path
        self._init_material_fields()

    def _init_material_fields(self) -> None:
        material = None
        if self.instance and self.instance.pk:
            material = (
                CaseMaterial.objects.filter(source_attachment_id=self.instance.pk)
                .prefetch_related("parties")
                .first()
            )
        if not material:
            return
        self.fields["sync_to_case_material"].initial = True
        self.fields["material_category"].initial = material.category
        self.fields["material_side"].initial = material.side or ""
        self.fields["material_parties"].initial = ",".join(
            str(pk) for pk in material.parties.values_list("id", flat=True)
        )
        self.fields["material_supervising_authority"].initial = str(material.supervising_authority_id or "")
        self.fields["material_type"].initial = str(material.type_id or "")
        self.fields["material_type_name"].initial = material.type_name

    def _has_existing_file(self) -> bool:
        return bool(
            str(getattr(self.instance, "file", "") or "").strip()
            or str(getattr(self.instance, "relative_file_path", "") or "").strip()
            or str(getattr(self.instance, "original_filename", "") or "").strip()
        )

    def _has_uploaded_file(self) -> bool:
        if not hasattr(self, "files") or self.files is None:
            return False
        try:
            return bool(self.files.get(self.add_prefix("file")))
        except Exception:
            return False

    def has_changed(self) -> bool:
        changed = super().has_changed()
        if not changed:
            return False
        if self._has_existing_file() or self._has_uploaded_file():
            return True
        return False

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        if not cleaned.get("sync_to_case_material"):
            return cleaned

        category = str(cleaned.get("material_category") or "").strip()
        if category not in {CaseMaterialCategory.PARTY, CaseMaterialCategory.NON_PARTY}:
            raise forms.ValidationError(_("同步到案件材料时必须选择材料位置。"))

        material_type = cleaned.get("material_type")
        material_type_name = str(cleaned.get("material_type_name") or "").strip()
        if not material_type and not material_type_name:
            raise forms.ValidationError(_("同步到案件材料时必须选择或填写材料类型。"))
        selected_type = None
        if material_type:
            try:
                selected_type = CaseMaterialType.objects.get(pk=int(str(material_type)), is_active=True)
            except (CaseMaterialType.DoesNotExist, TypeError, ValueError):
                raise forms.ValidationError(_("材料类型不存在或已停用。")) from None
            if selected_type.category != category:
                raise forms.ValidationError(_("材料类型必须与材料位置一致。"))
            if selected_type.name == OTHER_MATERIAL_TYPE_NAME and not material_type_name:
                raise forms.ValidationError(_("选择其它材料时必须填写自定义类型名称。"))

        if category == CaseMaterialCategory.PARTY and not cleaned.get("material_side"):
            raise forms.ValidationError(_("当事人材料必须选择我方或对方。"))
        if category == CaseMaterialCategory.NON_PARTY and not cleaned.get("material_supervising_authority"):
            raise forms.ValidationError(_("非当事人材料必须选择主管机关。"))
        return cleaned

    def _parse_ids(self, value: object) -> list[int]:
        parsed: list[int] = []
        for part in str(value or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                parsed.append(int(part))
            except (TypeError, ValueError):
                continue
        return parsed

    def sync_case_material(self, *, user: object | None = None) -> None:
        if not self.instance or not self.instance.pk:
            return
        if not self._has_existing_file():
            return

        material_type_id = self._parse_ids(self.cleaned_data.get("material_type"))
        supervising_authority_id = self._parse_ids(self.cleaned_data.get("material_supervising_authority"))
        service = build_case_material_service()
        service.sync_attachment_to_material(
            attachment_id=int(self.instance.pk),
            include=bool(self.cleaned_data.get("sync_to_case_material")),
            category=str(self.cleaned_data.get("material_category") or ""),
            side=str(self.cleaned_data.get("material_side") or ""),
            party_ids=self._parse_ids(self.cleaned_data.get("material_parties")),
            supervising_authority_id=supervising_authority_id[0] if supervising_authority_id else None,
            type_id=material_type_id[0] if material_type_id else None,
            type_name=str(self.cleaned_data.get("material_type_name") or ""),
            user=user,
            perm_open_access=True,
        )

    def save(self, commit: bool = True) -> CaseLogAttachment:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("file")
        target_subdir = str(self.cleaned_data.get("target_subdir") or "").strip()
        has_existing_file = self._has_existing_file()

        from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService

        storage_service = CaseLogAttachmentStorageService()
        if uploaded_file:
            from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE

            saved = storage_service.save_attachment(
                uploaded_file,
                case_id=instance.log.case_id,
                target_subdir=target_subdir,
                log=instance.log,
                allowed_extensions=list(CASE_LOG_ALLOWED_EXTENSIONS),
                max_size_bytes=int(CASE_LOG_MAX_FILE_SIZE),
            )
            instance.file = saved.legacy_file_path
            instance.storage_root_type = saved.root_type
            instance.subdir_path = saved.subdir_path
            instance.relative_file_path = saved.relative_file_path
            instance.original_filename = saved.original_filename
        elif (
            instance.pk
            and has_existing_file
            and target_subdir
            and target_subdir != str(instance.subdir_path or "").strip()
        ):
            moved = storage_service.move_attachment(
                instance,
                case_id=instance.log.case_id,
                target_subdir=target_subdir,
            )
            instance.file = moved.legacy_file_path
            instance.storage_root_type = moved.root_type
            instance.subdir_path = moved.subdir_path
            instance.relative_file_path = moved.relative_file_path
            if not instance.original_filename:
                instance.original_filename = moved.original_filename

        if commit:
            instance.save()
        return instance


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    form = CaseLogAttachmentInlineForm
    extra = 1
    fields = (
        "file",
        "target_subdir",
        "file_link",
        "uploaded_at",
        "sync_to_case_material",
        "material_category",
        "material_side",
        "material_parties",
        "material_supervising_authority",
        "material_type",
        "material_type_name",
    )
    readonly_fields = ("file_link", "uploaded_at")
    autocomplete_fields = ("log",)

    @admin.display(description=_("当前文件"))
    def file_link(self, obj: CaseLogAttachment) -> str:
        if obj.pk and obj.log_id and obj.case_id and obj.original_filename:
            url = reverse("admin:cases_case_preview_log_attachment", args=[obj.case_id, obj.pk])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.original_filename)
        return obj.original_filename or "-"


class ReminderInline(BaseTabularInline):
    model = CaseLog.reminders.rel.related_model  # type: ignore[assignment]
    extra = 0
    fields = ("reminder_type", "content", "due_at", "include_in_important_time")
    verbose_name = "重要日期提醒"
    verbose_name_plural = "重要日期提醒"
    ordering = ("due_at",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):  # type: ignore[no-untyped-def]
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "include_in_important_time" and formfield is not None:
            formfield.label = _("同步到案件重要时间")
            formfield.help_text = _("同步到案件重要时间：勾选后会在案件详情的重要时间中展示，不会复制生成新数据。")
        return formfield


@admin.register(CaseLog)
class CaseLogAdmin(BaseModelAdmin):
    list_display = ("id", "case_link", "actor", "reminder_type", "reminder_time", "created_at", "updated_at")
    list_select_related = ("case", "actor")
    list_per_page = 50
    list_filter = ("created_at",)
    search_fields = ("content", "case__name")
    ordering = ("-created_at",)
    autocomplete_fields = ("case", "actor")
    exclude = ("actor", "source_subfolder")
    inlines = (ReminderInline, CaseLogAttachmentInline)
    change_form_template = "admin/cases/caselog/change_form.html"

    def get_urls(self) -> list[URLPattern]:
        urls: list[URLPattern] = super().get_urls()
        custom: list[URLPattern] = [
            path(
                "material-sync-options/<int:case_id>/",
                self.admin_site.admin_view(self.material_sync_options_view),
                name="cases_caselog_material_sync_options",
            ),
        ]
        return custom + urls

    @admin.display(description="案件名称", ordering="case__name")
    def case_link(self, obj: CaseLog) -> str:
        url = reverse("admin:cases_case_detail", args=[obj.case_id])
        return format_html('<a href="{}">{}</a>', url, obj.case)

    def save_model(
        self,
        request: HttpRequest,
        obj: CaseLog,
        form: ModelForm[CaseLog],
        change: bool,
    ) -> None:
        if not getattr(obj, "actor_id", None):
            user_id = getattr(request.user, "id", None)
            if user_id is not None:
                obj.actor_id = user_id
        super().save_model(request, obj, form, change)

    def save_formset(self, request: HttpRequest, form: ModelForm[CaseLog], formset: object, change: bool) -> None:
        super().save_formset(request, form, formset, change)
        if getattr(formset, "model", None) is not CaseLogAttachment:
            return
        for inline_form in getattr(formset, "forms", []):
            if not getattr(inline_form, "cleaned_data", None):
                continue
            if inline_form.cleaned_data.get("DELETE"):
                continue
            if hasattr(inline_form, "sync_case_material"):
                inline_form.sync_case_material(user=getattr(request, "user", None))

    def _normalize_case_id(self, value: object) -> int | None:
        value = getattr(value, "pk", value)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _resolve_material_sync_case_id(
        self,
        request: HttpRequest,
        context: dict[str, object] | None = None,
        obj: CaseLog | None = None,
    ) -> int | None:
        candidates: list[object] = [
            getattr(obj, "case_id", None),
            request.POST.get("case"),
            request.GET.get("case"),
        ]

        adminform = (context or {}).get("adminform")
        form = getattr(adminform, "form", None)
        if form is not None:
            candidates.extend(
                [
                    getattr(getattr(form, "instance", None), "case_id", None),
                    getattr(form, "initial", {}).get("case") if hasattr(form, "initial") else None,
                    getattr(form, "data", {}).get("case") if hasattr(form, "data") else None,
                ]
            )

        for candidate in candidates:
            case_id = self._normalize_case_id(candidate)
            if case_id:
                return case_id

        resolver_match = getattr(request, "resolver_match", None)
        object_id = getattr(resolver_match, "kwargs", {}).get("object_id") if resolver_match else None
        log_id = self._normalize_case_id(object_id)
        if log_id:
            return CaseLog.objects.filter(pk=log_id).values_list("case_id", flat=True).first()
        return None

    def _build_material_sync_payloads(self, case_id: int | None) -> dict[str, list[dict[str, str]]]:
        parties: list[dict[str, str]] = []
        authorities: list[dict[str, str]] = []
        if case_id:
            parties = [
                {
                    "value": str(p.id),
                    "label": str(p.client) if p.client_id else str(p),
                    "side": CaseMaterialSide.OUR
                    if getattr(getattr(p, "client", None), "is_our_client", False)
                    else CaseMaterialSide.OPPONENT,
                }
                for p in CaseParty.objects.filter(case_id=case_id).select_related("client").order_by("id")
            ]
            authorities = [
                {"value": str(a.id), "label": str(a)}
                for a in SupervisingAuthority.objects.filter(case_id=case_id).order_by("created_at", "id")
            ]

        return {
            "categories": [{"value": value, "label": str(label)} for value, label in CaseMaterialCategory.choices],
            "sides": [{"value": value, "label": str(label)} for value, label in CaseMaterialSide.choices],
            "parties": parties,
            "authorities": authorities,
            "types": [
                {
                    "value": str(t.id),
                    "label": t.name,
                    "category": t.category,
                    "name": t.name,
                    "is_other": "1" if t.name == OTHER_MATERIAL_TYPE_NAME else "",
                }
                for t in sorted(
                    CaseMaterialType.objects.filter(is_active=True).select_related("law_firm"),
                    key=lambda item: (
                        item.category,
                        DEFAULT_MATERIAL_TYPE_ORDER.get(item.category, {}).get(item.name, 999),
                        item.name,
                        item.id,
                    ),
                )
            ],
        }

    def material_sync_options_view(self, request: HttpRequest, case_id: int) -> JsonResponse:
        return JsonResponse(self._build_material_sync_payloads(case_id))

    def render_change_form(
        self,
        request: HttpRequest,
        context: dict[str, object],
        add: bool = False,
        change: bool = False,
        form_url: str = "",
        obj: CaseLog | None = None,
    ):
        payloads = self._build_material_sync_payloads(
            self._resolve_material_sync_case_id(request=request, context=context, obj=obj)
        )
        context["caselog_material_categories_json"] = payloads["categories"]
        context["caselog_material_sides_json"] = payloads["sides"]
        context["caselog_material_parties_json"] = payloads["parties"]
        context["caselog_material_authorities_json"] = payloads["authorities"]
        context["caselog_material_types_json"] = payloads["types"]
        context["caselog_material_options_url"] = reverse(
            "admin:cases_caselog_material_sync_options",
            args=[0],
        ).replace("/0/", "/__CASE_ID__/")
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)


@admin.register(CaseLogAttachment)
class CaseLogAttachmentAdmin(BaseModelAdmin):
    list_display = ("id", "log", "uploaded_at")
    search_fields = ("log__case__name",)
    autocomplete_fields = ("log",)

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        """隐藏 Admin 首页入口，但保留直接 URL 访问能力。"""
        return {}
