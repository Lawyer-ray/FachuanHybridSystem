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


def _serialize_client(client: Any) -> dict[str, Any]:
    return {
        "name": client.name,
        "client_type": client.client_type,
        "id_number": client.id_number,
        "phone": client.phone,
        "address": getattr(client, "address", None),
        "legal_representative": client.legal_representative,
        "legal_representative_id_number": getattr(client, "legal_representative_id_number", None),
        "is_our_client": client.is_our_client,
        "identity_docs": [
            {"doc_type": d.doc_type, "file_path": d.file_path}
            for d in client.identity_docs.all() if d.file_path
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
            for cl in client.property_clues.all()
        ],
    }


def serialize_case_obj(obj: Any) -> dict[str, Any]:
    """将单个 Case 实例序列化为 dict（供 CaseAdmin 和 ContractAdmin 共用）。"""
    return {
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
        "parties": [
            {"legal_status": p.legal_status, "client": _serialize_client(p.client)}
            for p in obj.parties.all()
        ],
        "assignments": [
            {"lawyer": {"real_name": a.lawyer.real_name, "phone": a.lawyer.phone, "username": a.lawyer.username}}
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
        "chats": [
            {"platform": ch.platform, "chat_id": ch.chat_id, "name": ch.name,
             "is_active": ch.is_active, "owner_id": ch.owner_id}
            for ch in obj.chats.all()
        ],
        "logs": [
            {
                "content": log.content,
                "created_at": log.created_at.isoformat(),
                "actor": {"real_name": log.actor.real_name, "phone": log.actor.phone, "username": log.actor.username},
                "attachments": [
                    {"file_path": att.file.name, "filename": att.file.name.split("/")[-1]}
                    for att in log.attachments.all() if att.file
                ],
                "reminders": [
                    {"reminder_type": r.reminder_type, "content": r.content,
                     "due_at": r.due_at.isoformat(), "metadata": r.metadata}
                    for r in log.reminders.all()
                ],
            }
            for log in obj.logs.all()
        ],
    }


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
        from apps.contracts.admin.contract_admin import serialize_contract_obj
        result = []
        for obj in queryset.prefetch_related(
            "parties__client__identity_docs",
            "parties__client__property_clues__attachments",
            "assignments__lawyer",
            "supervising_authorities",
            "case_numbers",
            "chats",
            "logs__actor",
            "logs__attachments",
            "logs__reminders",
            "contract__contract_parties__client__identity_docs",
            "contract__contract_parties__client__property_clues__attachments",
            "contract__assignments__lawyer",
            "contract__finalized_materials",
            "contract__supplementary_agreements__parties__client",
            "contract__payments__invoices",
            "contract__finance_logs__actor",
            "contract__reminders",
            "contract__client_payment_records",
        ):
            data = serialize_case_obj(obj)
            data["contract"] = serialize_contract_obj(obj.contract) if obj.contract else None
            result.append(data)
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
            "logs__attachments",
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
            for log in obj.logs.all():
                for att in log.attachments.all():
                    if att.file:
                        _add(att.file.name)
        return paths
