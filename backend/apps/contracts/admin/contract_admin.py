from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.http import HttpRequest
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
from apps.core.enums import CaseStage, CaseStatus

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


class FinalizedMaterialInline(BaseTabularInline):  # type: ignore[type-arg]
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


class ContractPartyInline(BaseTabularInline):  # type: ignore[type-arg]
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    show_change_link = True

    class Media:
        js = ("contracts/js/party_role_auto.js",)


class ContractAssignmentInline(BaseTabularInline):  # type: ignore[type-arg]
    model = ContractAssignment
    extra = 1
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]


class SupplementaryAgreementPartyInline(BaseTabularInline):  # type: ignore[type-arg]
    """补充协议当事人内联（嵌套在补充协议中）"""

    model = SupplementaryAgreementParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInline(BaseStackedInline):  # type: ignore[type-arg]
    """补充协议内联（在合同中）"""

    model = SupplementaryAgreement
    extra = 0
    fields = ("name",)
    show_change_link = True


# 如果支持嵌套 Admin，添加当事人内联到补充协议
if BaseModelAdmin is not admin.ModelAdmin:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]  # type: ignore[attr-defined]


@admin.register(Contract)
class ContractAdmin(ContractDisplayMixin, ContractSaveMixin, ContractActionMixin, AdminImportExportMixin, BaseModelAdmin):  # type: ignore[type-arg]
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
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]

    inlines: ClassVar = [
        ContractPartyInline,
        ContractAssignmentInline,
        SupplementaryAgreementInline,
        FinalizedMaterialInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).prefetch_related(
            "assignments__lawyer", "contract_parties__client"
        )

    def get_urls(self) -> list[Any]:
        from django.urls import path as urlpath

        urls = super().get_urls()
        custom = [
            urlpath(
                "<int:contract_id>/reorder-materials/",
                self.admin_site.admin_view(self.reorder_materials_view),
                name="contracts_contract_reorder_materials",
            ),
        ]
        return custom + urls

    def reorder_materials_view(self, request: HttpRequest, contract_id: int) -> Any:
        import json as json_mod

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"error": "Permission denied"}, status=403)
        try:
            data = json_mod.loads(request.body)
            ids: list[int] = data.get("ids", [])
            for i, pk in enumerate(ids):
                FinalizedMaterial.objects.filter(pk=pk, contract_id=contract_id).update(order=i)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.client.services.client_resolve_service import ClientResolveService
        from apps.contracts.services.contract_import_service import ContractImportService
        from apps.organization.services.lawyer_resolve_service import LawyerResolveService

        client_svc = ClientResolveService()
        lawyer_svc = LawyerResolveService()
        contract_svc = ContractImportService(client_resolve=client_svc, lawyer_resolve=lawyer_svc)

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
                errors.append(f"[{i}] {item.get('name', '?')}: {exc}")
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Contract]) -> list[dict[str, Any]]:  # type: ignore[override]
        result = []
        for obj in queryset.prefetch_related(
            "contract_parties__client__identity_docs",
            "contract_parties__client__property_clues__attachments",
            "assignments__lawyer",
            "finalized_materials",
            "supplementary_agreements__parties__client",
            "payments",
            "finance_logs__actor",
            "cases__parties__client",
            "cases__assignments__lawyer",
            "cases__supervising_authorities",
            "cases__case_numbers",
        ):
            result.append({
                "name": obj.name,
                "case_type": obj.case_type,
                "filing_number": obj.filing_number,
                "status": obj.status,
                "specified_date": str(obj.specified_date) if obj.specified_date else None,
                "start_date": str(obj.start_date) if obj.start_date else None,
                "end_date": str(obj.end_date) if obj.end_date else None,
                "is_archived": obj.is_archived,
                "fee_mode": obj.fee_mode,
                "fixed_amount": str(obj.fixed_amount) if obj.fixed_amount is not None else None,
                "risk_rate": str(obj.risk_rate) if obj.risk_rate is not None else None,
                "custom_terms": obj.custom_terms,
                "representation_stages": obj.representation_stages,
                "parties": [
                    {
                        "role": p.role,
                        "client": {
                            "name": p.client.name,
                            "client_type": p.client.client_type,
                            "id_number": p.client.id_number,
                            "phone": p.client.phone,
                            "address": p.client.address,
                            "legal_representative": p.client.legal_representative,
                            "legal_representative_id_number": p.client.legal_representative_id_number,
                            "is_our_client": p.client.is_our_client,
                            "identity_docs": [
                                {"doc_type": d.doc_type, "file_path": d.file_path}
                                for d in p.client.identity_docs.all() if d.file_path
                            ],
                            "property_clues": [
                                {
                                    "clue_type": c.clue_type,
                                    "content": c.content,
                                    "attachments": [
                                        {"file_path": a.file_path, "file_name": a.file_name}
                                        for a in c.attachments.all() if a.file_path
                                    ],
                                }
                                for c in p.client.property_clues.all()
                            ],
                        },
                    }
                    for p in obj.contract_parties.all()
                ],
                "assignments": [
                    {
                        "is_primary": a.is_primary,
                        "order": a.order,
                        "lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone},
                    }
                    for a in obj.assignments.all()
                ],
                "finalized_materials": [
                    {
                        "file_path": m.file_path,
                        "original_filename": m.original_filename,
                        "category": m.category,
                        "remark": m.remark,
                    }
                    for m in obj.finalized_materials.all() if m.file_path
                ],
                "supplementary_agreements": [
                    {
                        "name": sa.name,
                        "parties": [
                            {
                                "role": sp.role,
                                "client": {
                                    "name": sp.client.name,
                                    "client_type": sp.client.client_type,
                                    "id_number": sp.client.id_number,
                                    "phone": sp.client.phone,
                                    "legal_representative": sp.client.legal_representative,
                                    "is_our_client": sp.client.is_our_client,
                                },
                            }
                            for sp in sa.parties.all()
                        ],
                    }
                    for sa in obj.supplementary_agreements.all()
                ],
                "payments": [
                    {
                        "amount": str(p.amount),
                        "received_at": str(p.received_at),
                        "invoice_status": p.invoice_status,
                        "invoiced_amount": str(p.invoiced_amount),
                        "note": p.note,
                    }
                    for p in obj.payments.all()
                ],
                "finance_logs": [
                    {
                        "action": fl.action,
                        "level": fl.level,
                        "payload": fl.payload,
                        "actor": {"real_name": fl.actor.real_name, "phone": fl.actor.phone},
                    }
                    for fl in obj.finance_logs.all()
                ],
                "cases": [
                    {
                        "name": c.name,
                        "filing_number": c.filing_number,
                        "status": c.status,
                        "case_type": c.case_type,
                        "cause_of_action": c.cause_of_action,
                        "target_amount": str(c.target_amount) if c.target_amount is not None else None,
                        "preservation_amount": str(c.preservation_amount) if c.preservation_amount is not None else None,
                        "current_stage": c.current_stage,
                        "is_archived": c.is_archived,
                        "effective_date": str(c.effective_date) if c.effective_date else None,
                        "specified_date": str(c.specified_date) if c.specified_date else None,
                        "parties": [
                            {
                                "legal_status": p.legal_status,
                                "client": {
                                    "name": p.client.name,
                                    "client_type": p.client.client_type,
                                    "id_number": p.client.id_number,
                                    "phone": p.client.phone,
                                    "legal_representative": p.client.legal_representative,
                                    "is_our_client": p.client.is_our_client,
                                },
                            }
                            for p in c.parties.all()
                        ],
                        "assignments": [
                            {"lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone}}
                            for a in c.assignments.all()
                        ],
                        "supervising_authorities": [
                            {"name": sa.name, "authority_type": sa.authority_type}
                            for sa in c.supervising_authorities.all()
                        ],
                        "case_numbers": [
                            {"number": cn.number, "is_active": cn.is_active, "remarks": cn.remarks}
                            for cn in c.case_numbers.all()
                        ],
                    }
                    for c in obj.cases.all()
                ],
            })
        return result

    def get_file_paths(self, queryset: QuerySet[Contract]) -> list[str]:  # type: ignore[override]
        seen: set[str] = set()
        paths: list[str] = []

        def _add(p: str) -> None:
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        for obj in queryset.prefetch_related(
            "finalized_materials",
            "contract_parties__client__identity_docs",
            "contract_parties__client__property_clues__attachments",
        ):
            for m in obj.finalized_materials.all():
                _add(m.file_path)
            for p in obj.contract_parties.all():
                for d in p.client.identity_docs.all():
                    _add(d.file_path)
                for c in p.client.property_clues.all():
                    for a in c.attachments.all():
                        _add(a.file_path)
        return paths
