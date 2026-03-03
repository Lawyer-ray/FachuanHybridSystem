from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest

from apps.cases.admin.base import BaseModelAdmin, BaseStackedInline, BaseTabularInline
from apps.cases.admin.case_chat_admin import CaseChatInline
from apps.cases.admin.case_forms_admin import CaseAdminForm, SupervisingAuthorityInlineForm
from apps.cases.admin.mixins import (
    CaseAdminActionsMixin,
    CaseAdminSaveMixin,
    CaseAdminServiceMixin,
    CaseAdminViewsMixin,
)
from apps.cases.models import (
    Case,
    CaseAssignment,
    CaseLog,
    CaseLogAttachment,
    CaseNumber,
    CaseParty,
    SupervisingAuthority,
)
from apps.core.admin.mixins import AdminImportExportMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet


class CasePartyInline(BaseTabularInline):
    """案件当事人内联编辑组件"""

    model = CaseParty
    extra = 1
    fields = ("client", "legal_status")
    classes = ["contract-party-inline"]

    class Media:
        js = (
            "cases/admin_caseparty.js",
            "cases/admin_case_form.js",
        )
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("cases/admin_caseparty.css",)}


class CaseAssignmentInline(BaseTabularInline):
    model = CaseAssignment
    extra = 1


class SupervisingAuthorityInline(BaseTabularInline):
    """主管机关内联"""

    model = SupervisingAuthority
    form = SupervisingAuthorityInlineForm
    extra = 1
    fields = ("name", "authority_type")


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    extra = 0


class CaseNumberInline(BaseTabularInline):
    model = CaseNumber
    extra = 1
    fields = ("number", "is_active", "remarks")


class CaseLogInline(BaseStackedInline):
    model = CaseLog
    extra = 0
    fields = ("content", "created_at")
    exclude = ("actor",)
    readonly_fields = ("created_at",)
    show_change_link = True
    verbose_name = ""
    verbose_name_plural = "案件日志"

    if BaseModelAdmin is not admin.ModelAdmin:
        pass


@admin.register(Case)
class CaseAdmin(CaseAdminActionsMixin, CaseAdminSaveMixin, CaseAdminViewsMixin, CaseAdminServiceMixin, AdminImportExportMixin, BaseModelAdmin):
    form = CaseAdminForm
    list_display = ("id_link", "name_link", "status", "start_date", "effective_date", "is_archived")
    list_display_links = None
    list_filter = ("status", "is_archived")
    search_fields = ("name",)
    change_form_template = "admin/cases/case/change_form.html"
    readonly_fields = ("filing_number",)
    export_model_name = "case"
    actions = ["create_feishu_chat_for_selected_cases", "export_selected_as_json", "export_all_as_json"]

    class Media:
        js = (
            "cases/admin_case_form.js",
            "cases/js/autocomplete.js",
            "cases/js/autocomplete_init.js",
            "cases/js/case_log_sort.js",
            "cases/js/litigation_fee.js",
        )
        css = {"all": ("cases/css/case_log_admin.css",)}

    inlines = [
        CasePartyInline,
        CaseAssignmentInline,
        SupervisingAuthorityInline,
        CaseNumberInline,
        CaseLogInline,
        CaseChatInline,
    ]

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.cases.services.case_import_service import CaseImportService
        from apps.client.services.client_resolve_service import ClientResolveService
        from apps.contracts.services.contract_import_service import ContractImportService
        from apps.organization.services.lawyer_resolve_service import LawyerResolveService

        client_svc = ClientResolveService()
        lawyer_svc = LawyerResolveService()
        contract_svc = ContractImportService(client_resolve=client_svc, lawyer_resolve=lawyer_svc)
        case_svc = CaseImportService(
            contract_import=contract_svc, client_resolve=client_svc, lawyer_resolve=lawyer_svc
        )

        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            try:
                filing_number = item.get("filing_number")
                before = Case.objects.filter(filing_number=filing_number).exists() if filing_number else False
                case_svc.import_one(item)
                if before:
                    skipped += 1
                else:
                    success += 1
            except Exception as exc:
                errors.append(f"[{i}] {item.get('name', '?')}: {exc}")
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Case]) -> list[dict[str, Any]]:  # type: ignore[override]
        result = []
        for obj in queryset.prefetch_related(
            "parties__client__identity_docs",
            "parties__client__property_clues__attachments",
            "assignments__lawyer",
            "supervising_authorities",
            "case_numbers",
            "contract__contract_parties__client__identity_docs",
            "contract__contract_parties__client__property_clues__attachments",
            "contract__assignments__lawyer",
            "contract__finalized_materials",
            "contract__supplementary_agreements__parties__client",
            "contract__payments",
            "contract__finance_logs__actor",
        ):
            contract_data = None
            if obj.contract:
                c = obj.contract
                contract_data = {
                    "name": c.name,
                    "case_type": c.case_type,
                    "filing_number": c.filing_number,
                    "status": c.status,
                    "specified_date": str(c.specified_date) if c.specified_date else None,
                    "start_date": str(c.start_date) if c.start_date else None,
                    "end_date": str(c.end_date) if c.end_date else None,
                    "is_archived": c.is_archived,
                    "fee_mode": c.fee_mode,
                    "fixed_amount": str(c.fixed_amount) if c.fixed_amount is not None else None,
                    "risk_rate": str(c.risk_rate) if c.risk_rate is not None else None,
                    "custom_terms": c.custom_terms,
                    "representation_stages": c.representation_stages,
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
                                        "clue_type": cl.clue_type,
                                        "content": cl.content,
                                        "attachments": [
                                            {"file_path": a.file_path, "file_name": a.file_name}
                                            for a in cl.attachments.all() if a.file_path
                                        ],
                                    }
                                    for cl in p.client.property_clues.all()
                                ],
                            },
                        }
                        for p in c.contract_parties.all()
                    ],
                    "assignments": [
                        {"is_primary": a.is_primary, "order": a.order,
                         "lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone}}
                        for a in c.assignments.all()
                    ],
                    "finalized_materials": [
                        {"file_path": m.file_path, "original_filename": m.original_filename,
                         "category": m.category, "remark": m.remark}
                        for m in c.finalized_materials.all() if m.file_path
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
                        for sa in c.supplementary_agreements.all()
                    ],
                    "payments": [
                        {"amount": str(p.amount), "received_at": str(p.received_at),
                         "invoice_status": p.invoice_status, "invoiced_amount": str(p.invoiced_amount),
                         "note": p.note}
                        for p in c.payments.all()
                    ],
                    "finance_logs": [
                        {"action": fl.action, "level": fl.level, "payload": fl.payload,
                         "actor": {"real_name": fl.actor.real_name, "phone": fl.actor.phone}}
                        for fl in c.finance_logs.all()
                    ],
                }
            result.append({
                "name": obj.name,
                "filing_number": obj.filing_number,
                "status": obj.status,
                "case_type": obj.case_type,
                "cause_of_action": obj.cause_of_action,
                "target_amount": str(obj.target_amount) if obj.target_amount is not None else None,
                "preservation_amount": str(obj.preservation_amount) if obj.preservation_amount is not None else None,
                "current_stage": obj.current_stage,
                "is_archived": obj.is_archived,
                "effective_date": str(obj.effective_date) if obj.effective_date else None,
                "specified_date": str(obj.specified_date) if obj.specified_date else None,
                "contract": contract_data,
                "parties": [
                    {
                        "legal_status": p.legal_status,
                        "client": {
                            "name": p.client.name,
                            "client_type": p.client.client_type,
                            "id_number": p.client.id_number,
                            "phone": p.client.phone,
                            "legal_representative": p.client.legal_representative,
                            "legal_representative_id_number": p.client.legal_representative_id_number,
                            "is_our_client": p.client.is_our_client,
                            "identity_docs": [
                                {"doc_type": d.doc_type, "file_path": d.file_path}
                                for d in p.client.identity_docs.all() if d.file_path
                            ],
                            "property_clues": [
                                {
                                    "clue_type": cl.clue_type,
                                    "content": cl.content,
                                    "attachments": [
                                        {"file_path": a.file_path, "file_name": a.file_name}
                                        for a in cl.attachments.all() if a.file_path
                                    ],
                                }
                                for cl in p.client.property_clues.all()
                            ],
                        },
                    }
                    for p in obj.parties.all()
                ],
                "assignments": [
                    {"lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone}}
                    for a in obj.assignments.all()
                ],
                "supervising_authorities": [
                    {"name": sa.name, "authority_type": sa.authority_type}
                    for sa in obj.supervising_authorities.all()
                ],
                "case_numbers": [
                    {"number": cn.number, "is_active": cn.is_active, "remarks": cn.remarks}
                    for cn in obj.case_numbers.all()
                ],
            })
        return result

    def get_file_paths(self, queryset: QuerySet[Case]) -> list[str]:  # type: ignore[override]
        seen: set[str] = set()
        paths: list[str] = []

        def _add(p: str) -> None:
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        for obj in queryset.prefetch_related(
            "contract__finalized_materials",
            "parties__client__identity_docs",
            "parties__client__property_clues__attachments",
            "contract__contract_parties__client__identity_docs",
            "contract__contract_parties__client__property_clues__attachments",
        ):
            if obj.contract:
                for m in obj.contract.finalized_materials.all():
                    _add(m.file_path)
                for p in obj.contract.contract_parties.all():
                    for d in p.client.identity_docs.all():
                        _add(d.file_path)
                    for cl in p.client.property_clues.all():
                        for a in cl.attachments.all():
                            _add(a.file_path)
            for p in obj.parties.all():
                for d in p.client.identity_docs.all():
                    _add(d.file_path)
                for cl in p.client.property_clues.all():
                    for a in cl.attachments.all():
                        _add(a.file_path)
        return paths
