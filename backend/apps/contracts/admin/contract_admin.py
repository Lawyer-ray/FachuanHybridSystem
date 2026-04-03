from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from apps.contracts.admin.mixins.action_mixin import ContractActionMixin
from apps.contracts.admin.mixins.display_mixin import ContractDisplayMixin
from apps.contracts.admin.mixins.save_mixin import ContractSaveMixin
from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    FinalizedMaterial,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.core.admin.mixins import AdminImportExportMixin
from apps.core.models.enums import CaseStage, CaseStatus

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
    from django.db.models import QuerySet
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline


class FinalizedMaterialAdminForm(forms.ModelForm[FinalizedMaterial]):
    file = forms.FileField(
        required=False,
        label=_("上传文件"),
        help_text=_("仅支持 PDF，最大 20MB"),
    )

    class Meta:
        model = FinalizedMaterial
        fields = ("file", "category")

    def save(self, commit: bool = True) -> FinalizedMaterial:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file:
            from apps.contracts.admin.wiring_admin import get_material_service

            svc = get_material_service()
            contract_id: int = instance.contract_id or self.instance.contract_id
            rel_path, original_name = svc.save_material_file(uploaded_file, contract_id)
            instance.file_path = rel_path
            instance.original_filename = original_name
        if commit:
            instance.save()
        return instance


class FinalizedMaterialInline(BaseTabularInline):
    model = FinalizedMaterial
    form = FinalizedMaterialAdminForm
    extra = 1
    fields: ClassVar = ("file", "category", "filename_link", "uploaded_at")
    readonly_fields: ClassVar = ("filename_link", "uploaded_at")

    @admin.display(description=_("原始文件名"))
    def filename_link(self, obj: FinalizedMaterial) -> str:
        from django.utils.html import format_html

        if obj.file_path and obj.original_filename:
            url = f"/media/{obj.file_path}"
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.original_filename)
        return obj.original_filename or "-"

    def delete_model(self, request: HttpRequest, obj: FinalizedMaterial) -> None:
        from apps.contracts.admin.wiring_admin import get_material_service

        get_material_service().delete_material_file(obj.file_path)
        obj.delete()

    class Media:
        css = {"all": ("contracts/css/finalized_material_inline.css",)}


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]
    show_change_link = True

    class Media:
        js = ("contracts/js/party_role_auto.js",)


class ContractAssignmentInline(BaseTabularInline):
    model = ContractAssignment
    extra = 1
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]


class SupplementaryAgreementPartyInline(BaseTabularInline):
    """补充协议当事人内联（嵌套在补充协议中）"""

    model = SupplementaryAgreementParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInline(BaseStackedInline):
    """补充协议内联（在合同中）"""

    model = SupplementaryAgreement
    extra = 0
    fields = ("name",)
    show_change_link = True


# 如果支持嵌套 Admin，添加当事人内联到补充协议
if BaseModelAdmin is not admin.ModelAdmin:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]  # type: ignore[attr-defined]


def serialize_contract_obj(obj: Any) -> dict[str, Any]:
    """将单个 Contract 实例序列化为 dict（供 ContractAdmin 和 CaseAdmin 共用）。"""
    from apps.contracts.services.contract.contract_export_serializer_service import (
        serialize_contract_obj as serialize_contract_obj_service,
    )

    result: dict[str, Any] = serialize_contract_obj_service(obj)
    return result


@admin.register(Contract)
class ContractAdmin(
    ContractDisplayMixin, ContractSaveMixin, ContractActionMixin, AdminImportExportMixin, BaseModelAdmin
):
    class ContractAdminForm(forms.ModelForm[Contract]):
        representation_stages = forms.MultipleChoiceField(
            choices=CaseStage.choices,
            required=False,
            widget=forms.SelectMultiple,
            label=_("代理阶段"),
        )

        class Meta:
            model = Contract
            fields = "__all__"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            if not getattr(self.instance, "pk", None):
                self.fields["status"].initial = CaseStatus.ACTIVE
                self.fields["specified_date"].initial = timezone.localdate()
            self.fields["representation_stages"].initial = list(
                getattr(self.instance, "representation_stages", []) or []
            )

        def clean(self) -> dict[str, Any]:
            cleaned = super().clean() or {}
            try:
                from apps.contracts.validators import normalize_representation_stages

                ctype = cleaned.get("case_type")
                rep = cleaned.get("representation_stages") or []
                cleaned["representation_stages"] = normalize_representation_stages(ctype, rep, strict=False)
            except Exception:
                logger.exception("操作失败")
            return cleaned

    form = ContractAdminForm
    list_display = (
        "id",
        "name_link",
        "case_type",
        "status",
        "start_date",
        "end_date",
        "get_primary_lawyer",
        "fee_mode",
        "fixed_amount",
        "risk_rate",
        "is_archived",
    )
    list_filter = ("case_type", "status", "fee_mode", "is_archived")
    search_fields = ("name",)
    readonly_fields = ("get_primary_lawyer_display", "filing_number")
    export_model_name = "contract"
    import_required_fields = ("name",)
    actions = ["export_selected_as_json", "export_all_as_json"]

    inlines: ClassVar = [
        ContractPartyInline,
        ContractAssignmentInline,
        SupplementaryAgreementInline,
        FinalizedMaterialInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"
    change_list_template = "admin/contracts/contract/change_list.html"

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).prefetch_related("assignments__lawyer", "contract_parties__client")

    def get_urls(self) -> list[Any]:
        from django.urls import path as urlpath

        urls = super().get_urls()
        custom = [
            urlpath(
                "batch-folder-binding/",
                self.admin_site.admin_view(self.batch_folder_binding_view),
                name="contracts_contract_batch_folder_binding",
            ),
            urlpath(
                "batch-folder-binding/preview/",
                self.admin_site.admin_view(self.batch_folder_binding_preview_view),
                name="contracts_contract_batch_folder_binding_preview",
            ),
            urlpath(
                "batch-folder-binding/save/",
                self.admin_site.admin_view(self.batch_folder_binding_save_view),
                name="contracts_contract_batch_folder_binding_save",
            ),
            urlpath(
                "batch-folder-binding/open-folder/",
                self.admin_site.admin_view(self.batch_folder_binding_open_folder_view),
                name="contracts_contract_batch_folder_binding_open_folder",
            ),
            urlpath(
                "<int:contract_id>/reorder-materials/",
                self.admin_site.admin_view(self.reorder_materials_view),
                name="contracts_contract_reorder_materials",
            ),
            urlpath(
                "oa-sync/",
                self.admin_site.admin_view(self.oa_sync_view),
                name="contracts_contract_oa_sync",
            ),
            urlpath(
                "oa-sync/start/",
                self.admin_site.admin_view(self.oa_sync_start_view),
                name="contracts_contract_oa_sync_start",
            ),
            urlpath(
                "oa-sync/status/<int:session_id>/",
                self.admin_site.admin_view(self.oa_sync_status_view),
                name="contracts_contract_oa_sync_status",
            ),
            urlpath(
                "oa-sync/save/",
                self.admin_site.admin_view(self.oa_sync_save_view),
                name="contracts_contract_oa_sync_save",
            ),
        ]
        return custom + urls

    def reorder_materials_view(self, request: HttpRequest, contract_id: int) -> Any:
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"error": "Permission denied"}, status=403)
        try:
            data = json.loads(request.body)
            ids: list[int] = data.get("ids", [])
            for i, pk in enumerate(ids):
                FinalizedMaterial.objects.filter(pk=pk, contract_id=contract_id).update(order=i)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    def batch_folder_binding_view(self, request: HttpRequest) -> TemplateResponse:
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        service = get_contract_batch_folder_binding_service()
        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("合同批量绑定文件夹"),
                "opts": self.model._meta,
                "cards": service.list_unbound_case_type_cards(),
                "batch_folder_binding_config": {
                    "previewUrl": "/admin/contracts/contract/batch-folder-binding/preview/",
                    "saveUrl": "/admin/contracts/contract/batch-folder-binding/save/",
                    "openFolderUrl": "/admin/contracts/contract/batch-folder-binding/open-folder/",
                    "changeListUrl": "/admin/contracts/contract/",
                },
            }
        )
        return TemplateResponse(request, "admin/contracts/contract/batch_folder_binding.html", context)

    def oa_sync_view(self, request: HttpRequest) -> TemplateResponse:
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        service = get_contract_oa_sync_service()
        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("合同OA信息同步"),
                "opts": self.model._meta,
                "oa_sync_initial_contracts": service.list_missing_oa_contracts(),
                "oa_sync_config": {
                    "startUrl": "/admin/contracts/contract/oa-sync/start/",
                    "statusUrl": "/admin/contracts/contract/oa-sync/status/__SESSION_ID__/",
                    "saveUrl": "/admin/contracts/contract/oa-sync/save/",
                    "changeListUrl": "/admin/contracts/contract/",
                },
            }
        )
        return TemplateResponse(request, "admin/contracts/contract/oa_sync.html", context)

    def oa_sync_start_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        try:
            service = get_contract_oa_sync_service()
            session = service.create_or_get_active_session(started_by=request.user)
            session = service.submit_session_task(session=session)
            return JsonResponse(
                {
                    "success": True,
                    "message": _("同步任务已启动"),
                    "session_id": int(session.id),
                }
            )
        except Exception as exc:
            logger.exception("contract_oa_sync_start_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def oa_sync_save_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        payload = self._parse_json_payload(request)
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            result = get_contract_oa_sync_service().save_manual_contract_oa_fields(updates=entries)
            message = _("保存成功") if result.get("error_count", 0) == 0 else _("部分保存成功，请检查错误项")
            return JsonResponse({"success": True, "message": message, **result})
        except Exception as exc:
            logger.exception("contract_oa_sync_save_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def oa_sync_status_view(self, request: HttpRequest, session_id: int) -> JsonResponse:
        if request.method != "GET":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_view_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        service = get_contract_oa_sync_service()
        session = service.get_session(session_id=session_id)
        if session is None:
            return JsonResponse({"success": False, "message": _("会话不存在")}, status=404)

        return JsonResponse({"success": True, **service.build_status_payload(session=session)})

    def batch_folder_binding_preview_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        case_type_roots = payload.get("case_type_roots")
        if not isinstance(case_type_roots, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            data = get_contract_batch_folder_binding_service().preview(case_type_roots=case_type_roots)
            return JsonResponse({"success": True, **data})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_preview_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def batch_folder_binding_save_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        case_type_roots = payload.get("case_type_roots")
        contract_selections = payload.get("contract_selections")
        if not isinstance(case_type_roots, list) or not isinstance(contract_selections, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            result = get_contract_batch_folder_binding_service().save(
                case_type_roots=case_type_roots,
                contract_selections=contract_selections,
            )
            return JsonResponse({"success": True, **result})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_save_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def batch_folder_binding_open_folder_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        root_path = str(payload.get("root_path") or "").strip()
        folder_path = str(payload.get("folder_path") or "").strip()
        if not root_path or not folder_path:
            return JsonResponse({"success": False, "message": _("缺少路径参数")}, status=400)

        try:
            get_contract_batch_folder_binding_service().open_folder(root_path=root_path, folder_path=folder_path)
            return JsonResponse({"success": True, "message": _("已打开文件夹")})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_open_folder_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def _parse_json_payload(self, request: HttpRequest) -> dict[str, Any]:
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.contracts.services.contract_import_service import build_contract_import_service_for_admin

        contract_svc = build_contract_import_service_for_admin()

        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            try:
                filing_number = item.get("filing_number")
                before = Contract.objects.filter(filing_number=filing_number).exists() if filing_number else False
                contract_svc.resolve(item)
                if before:
                    skipped += 1
                else:
                    success += 1
            except Exception as exc:
                logger.exception("导入合同失败", extra={"index": i, "contract_name": item.get("name", "?")})
                errors.append(f"[{i}] {item.get('name', '?')} ({type(exc).__name__}): {exc}")
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Contract]) -> list[dict[str, Any]]:
        result = []
        for obj in queryset.prefetch_related(
            "contract_parties__client__identity_docs",
            "contract_parties__client__property_clues__attachments",
            "assignments__lawyer",
            "finalized_materials",
            "supplementary_agreements__parties__client",
            "payments__invoices",
            "finance_logs__actor",
            "client_payment_records",
            "cases__parties__client__identity_docs",
            "cases__parties__client__property_clues__attachments",
            "cases__assignments__lawyer",
            "cases__supervising_authorities",
            "cases__case_numbers",
            "cases__chats",
            "cases__logs__actor",
            "cases__logs__attachments",
        ):
            result.append(serialize_contract_obj(obj))
        return result

    def get_file_paths(self, queryset: QuerySet[Contract]) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []

        def _add(p: str) -> None:
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        for obj in queryset.prefetch_related(
            "finalized_materials",
            "client_payment_records",
            "payments__invoices",
            "contract_parties__client__identity_docs",
            "contract_parties__client__property_clues__attachments",
        ):
            for m in obj.finalized_materials.all():
                _add(m.file_path)
            for r in obj.client_payment_records.all():
                _add(r.image_path)
            for p in obj.payments.all():
                for inv in p.invoices.all():
                    _add(inv.file_path)
            for p in obj.contract_parties.all():
                for d in p.client.identity_docs.all():
                    _add(d.file_path)
                for c in p.client.property_clues.all():
                    for a in c.attachments.all():
                        _add(a.file_path)
        return paths
