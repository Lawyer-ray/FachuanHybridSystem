from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib import admin
from django.http import HttpRequest

from apps.cases.admin.base_admin import BaseModelAdmin, BaseStackedInline, BaseTabularInline
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


class CaseNumberInline(BaseStackedInline):
    model = CaseNumber
    extra = 1
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("number", "document_name", "is_active"),
                    "document_file",
                    "document_content",
                )
            },
        ),
        (
            None,
            {
                "classes": ("case-number-execution-fieldset",),
                "fields": (
                    ("execution_cutoff_date", "execution_paid_amount"),
                    ("execution_use_deduction_order", "execution_year_days", "execution_date_inclusion"),
                    "execution_manual_text",
                )
            },
        ),
    )


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


def serialize_case_obj(obj: Case) -> dict[str, object]:
    """将单个 Case 实例序列化为 dict（供 CaseAdmin 和 ContractAdmin 共用）。"""
    from apps.cases.services.case.case_export_serializer_service import serialize_case_obj as serialize_case_obj_service

    return serialize_case_obj_service(obj)


@admin.register(Case)
class CaseAdmin(
    CaseAdminActionsMixin,
    CaseAdminSaveMixin,
    CaseAdminViewsMixin,
    CaseAdminServiceMixin,
    AdminImportExportMixin,
    BaseModelAdmin,
):
    form = CaseAdminForm
    list_display = ("id_link", "name_link", "status", "start_date", "effective_date", "is_archived")
    list_display_links = None
    list_filter = ("status", "is_archived")
    search_fields = ("name",)
    change_form_template = "admin/cases/case/change_form.html"
    readonly_fields = ("filing_number",)
    export_model_name = "case"
    import_required_fields = ("name",)
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
        self, data_list: list[dict[str, object]], user: str, zip_file: object
    ) -> tuple[int, int, list[str]]:
        from apps.cases.services.case_import_service import build_case_import_service_for_admin

        case_svc = build_case_import_service_for_admin()
        admin_service = self._get_case_admin_service()
        return admin_service.import_cases_from_json_data(data_list, case_import_service=case_svc)

    def serialize_queryset(self, queryset: QuerySet[Case]) -> list[dict[str, object]]:  # type: ignore[override]
        service = self._get_case_admin_service()
        return service.serialize_queryset_for_export(queryset)

    def get_file_paths(self, queryset: QuerySet[Case]) -> list[str]:  # type: ignore[override]
        service = self._get_case_admin_service()
        return service.collect_file_paths_for_export(queryset)
