"""Module for views."""

from __future__ import annotations

import json as json_mod
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case

if TYPE_CHECKING:
    from apps.cases.services.case.case_admin_service import CaseAdminService

logger = logging.getLogger("apps.cases")


def _log_inline_formset(inline_formset: object, logger: logging.Logger) -> None:
    """记录 inline formset 的错误信息"""
    formset = inline_formset.formset
    for i, f in enumerate(formset.forms):
        if f.errors:
            logger.warning(
                "[CaseAdmin.changeform_view] Inline %s form[%s] errors: %s",
                formset.prefix,
                i,
                f.errors,
            )
    logger.info(
        "[CaseAdmin.changeform_view] Inline %s errors: %s, non_form_errors: %s",
        formset.prefix,
        formset.errors,
        formset.non_form_errors(),
    )
    logger.info(
        "[CaseAdmin.changeform_view] Inline %s is_valid: %s",
        formset.prefix,
        formset.is_valid(),
    )
    for nested in getattr(inline_formset, "inline_admin_formsets", []):
        nested_formset = nested.formset
        logger.info(
            "[CaseAdmin.changeform_view] Nested %s errors: %s",
            nested_formset.prefix,
            nested_formset.errors,
        )
        logger.info(
            "[CaseAdmin.changeform_view] Nested %s is_valid: %s",
            nested_formset.prefix,
            nested_formset.is_valid(),
        )
        for i, nf in enumerate(nested_formset.forms):
            if nf.errors:
                logger.warning(
                    "[CaseAdmin.changeform_view] Nested %s form[%s] errors: %s",
                    nested_formset.prefix,
                    i,
                    nf.errors,
                )


class CaseAdminViewsMixin:
    def id_link(self, obj: Case) -> str:
        change_url = reverse("admin:cases_case_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', change_url, obj.pk)

    id_link.short_description = "ID"  # type: ignore[attr-defined]
    id_link.admin_order_field = "id"  # type: ignore[attr-defined]

    def name_link(self, obj: Case) -> str:
        detail_url = reverse("admin:cases_case_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', detail_url, obj.name)

    name_link.short_description = _("案件名称")  # type: ignore[attr-defined]
    name_link.admin_order_field = "name"  # type: ignore[attr-defined]

    def get_urls(self) -> list[URLPattern]:
        urls: list[URLPattern] = super().get_urls()  # type: ignore[misc]
        custom_urls: list[URLPattern] = [
            path(
                "<int:object_id>/detail/",
                self.admin_site.admin_view(self.detail_view),  # type: ignore[attr-defined]
                name="cases_case_detail",
            ),
            path(
                "<int:object_id>/materials/",
                self.admin_site.admin_view(self.materials_view),  # type: ignore[attr-defined]
                name="cases_case_materials",
            ),
            path(
                "<int:object_id>/mock-trial/",
                self.admin_site.admin_view(self.mock_trial_view),  # type: ignore[attr-defined]
                name="cases_case_mock_trial",
            ),
            path(
                "litigation-fee-calculator/",
                self.admin_site.admin_view(self.litigation_fee_calculator_view),  # type: ignore[attr-defined]
                name="cases_litigation_fee_calculator",
            ),
        ]
        return custom_urls + urls

    def mock_trial_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        case = self._get_case_with_relations(object_id)
        if case is None:
            raise Http404(_("案件不存在"))
        if not self.has_view_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied
        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": _("模拟庭审: %(name)s") % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
            }
        )
        return render(request, "litigation_ai/mock_trial.html", context)

    def litigation_fee_calculator_view(self, request: HttpRequest) -> HttpResponse:
        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "title": _("诉讼费用计算器"),
                "opts": self.model._meta,  # type: ignore[attr-defined]
            }
        )
        return render(request, "admin/cases/litigation_fee_calculator.html", context)

    def detail_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        case = self._get_case_with_relations(object_id)

        if case is None:
            raise Http404(_("案件不存在"))

        if not self.has_view_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied

        service = self._get_case_admin_service()  # type: ignore[attr-defined]

        our_legal_statuses = [
            party.legal_status
            for party in case.parties.all()
            if getattr(party.client, "is_our_client", False) and party.legal_status
        ]

        is_our_party_all_defendant = bool(our_legal_statuses) and all(
            status == "defendant" for status in our_legal_statuses
        )

        matched_folder_templates = (
            service.get_matched_folder_templates(case.case_type, our_legal_statuses)
            if case.case_type
            else str(_("未设置案件类型"))
        )

        matched_case_file_templates, case_file_templates_missing_reason = service.get_case_file_templates_for_detail(
            case
        )

        grouped_case_file_templates = service.group_templates_by_sub_type(
            matched_case_file_templates,
            service.get_case_file_sub_type_choices(),
        )

        matched_folder_templates_list = (
            service.get_matched_folder_templates_list(case.case_type, our_legal_statuses) if case.case_type else []
        )

        our_legal_entities = service.build_our_legal_entities(case)
        our_legal_entities_json = json_mod.dumps(our_legal_entities, ensure_ascii=False)
        our_parties = service.build_our_parties(case)
        our_parties_json = json_mod.dumps(our_parties, ensure_ascii=False)
        respondents = service.build_respondents(case)
        respondents_json = json_mod.dumps(respondents, ensure_ascii=False)

        case_materials_view = self._build_case_materials_view(request, case)

        template_binding_service = self._get_case_template_binding_service()  # type: ignore[attr-defined]
        bound_templates = template_binding_service.get_bindings_for_case(case.id)
        bound_templates_json = json_mod.dumps(bound_templates, ensure_ascii=False)

        unified_templates = template_binding_service.get_unified_templates(case.id)
        unified_templates_json = json_mod.dumps(unified_templates, ensure_ascii=False)

        has_preservation_template, has_delay_delivery_template = service.detect_special_template_flags(
            unified_templates
        )

        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": _("案件详情: %(name)s") % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_change_permission": self.has_change_permission(request, case),  # type: ignore[attr-defined]
                "matched_folder_templates": matched_folder_templates,
                "matched_case_file_templates": matched_case_file_templates,
                "matched_folder_templates_list": matched_folder_templates_list,
                "case_file_templates_missing_reason": case_file_templates_missing_reason,
                "grouped_case_file_templates": grouped_case_file_templates,
                "can_generate_folder": bool(matched_folder_templates and "无匹配" not in matched_folder_templates),
                "folder_disabled_reason": self._get_folder_disabled_reason_v2(matched_folder_templates),
                "our_legal_entities_json": our_legal_entities_json,
                "has_our_legal_entities": bool(our_legal_entities),
                "our_legal_entities_count": len(our_legal_entities),
                "our_parties_json": our_parties_json,
                "has_our_parties": bool(our_parties),
                "our_parties_count": len(our_parties),
                "case_materials_view": case_materials_view,
                "bound_templates": bound_templates,
                "bound_templates_json": bound_templates_json,
                "unified_templates_json": unified_templates_json,
                "respondents_json": respondents_json,
                "has_respondents": bool(respondents),
                "has_preservation_template": has_preservation_template,
                "has_delay_delivery_template": has_delay_delivery_template,
                "is_our_party_all_defendant": is_our_party_all_defendant,
            }
        )

        return render(request, "admin/cases/case/detail.html", context)

    @staticmethod
    def _group_templates_by_sub_type(
        templates: list[dict[str, object]],
        sub_type_choices: list[tuple[str, str]],
    ) -> list[tuple[str, list[dict[str, object]]]]:
        from apps.cases.services.case.case_admin_service import CaseAdminService

        return CaseAdminService().group_templates_by_sub_type(templates, sub_type_choices)

    def _build_case_materials_view(self, request: HttpRequest, case: Case) -> dict[str, object]:
        material_service = self._get_case_material_service()  # type: ignore[attr-defined]
        return material_service.get_case_materials_view(
            case_id=case.id,
            user=getattr(request, "user", None),
            org_access=getattr(request, "org_access", None),
            perm_open_access=getattr(request, "perm_open_access", False),
        )

    def materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        case = self._get_case_with_relations(object_id)
        if case is None:
            raise Http404(_("案件不存在"))

        if not self.has_change_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied

        user = getattr(request, "user", None)
        law_firm_id = getattr(user, "law_firm_id", None) if user else None

        material_service = self._get_case_material_service()  # type: ignore[attr-defined]
        admin_service = self._get_case_admin_service()  # type: ignore[attr-defined]
        payload = admin_service.build_materials_view_payload(
            case=case,
            material_service=material_service,
            law_firm_id=law_firm_id,
        )
        scan_session_id = (request.GET.get("scan_session") or "").strip()
        open_scan_flag = (request.GET.get("open_scan") or "").strip().lower() in {"1", "true", "yes", "on"}
        open_scan = bool(scan_session_id) or open_scan_flag

        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": _("上传/绑定材料: %(name)s") % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "detail_url": reverse("admin:cases_case_detail", args=[case.pk]),
                "party_types_json": json_mod.dumps(payload["party_types"], ensure_ascii=False),
                "non_party_types_json": json_mod.dumps(payload["non_party_types"], ensure_ascii=False),
                "our_case_parties_json": json_mod.dumps(payload["our_parties"], ensure_ascii=False),
                "opponent_case_parties_json": json_mod.dumps(payload["opponent_parties"], ensure_ascii=False),
                "supervising_authorities_json": json_mod.dumps(payload["authorities"], ensure_ascii=False),
                "scan_session_id": scan_session_id,
                "open_scan": open_scan,
            }
        )

        return render(request, "admin/cases/case/materials.html", context)

    def _get_case_with_relations(self, case_id: int) -> Case | None:
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        return service.get_case_with_admin_relations(case_id)

    def _get_folder_disabled_reason(self, case: Case) -> str:
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        matched = service.get_matched_folder_templates(case.case_type) if case.case_type else ""
        if not matched or "无匹配" in matched:
            return str(_("无匹配的文件夹模板"))
        return ""

    def _get_folder_disabled_reason_v2(self, matched_folder_templates: str) -> str:
        if not matched_folder_templates or "无匹配" in matched_folder_templates:
            return str(_("无匹配的文件夹模板"))
        return ""

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        logger = logging.getLogger(__name__)

        if request.method == "POST":
            logger.info("[CaseAdmin.changeform_view] POST request, object_id=%s", object_id)

        response = super().changeform_view(request, object_id, form_url, extra_context)  # type: ignore[misc]

        if request.method == "POST":
            self._log_post_response(response, logger)

        return response  # type: ignore[no-any-return]

    @staticmethod
    def _log_post_response(response: HttpResponse, logger: logging.Logger) -> None:
        logger.info("[CaseAdmin.changeform_view] Response status: %s", response.status_code)
        ctx = getattr(response, "context_data", None)
        if not ctx:
            return
        if "adminform" in ctx:
            form = ctx["adminform"].form
            logger.info("[CaseAdmin.changeform_view] Form errors: %s", form.errors)
            logger.info("[CaseAdmin.changeform_view] Form is_valid: %s", not form.errors)
        for inline_formset in ctx.get("inline_admin_formsets", []):
            _log_inline_formset(inline_formset, logger)

    def contract_folder_path_display(self, obj: Case) -> str:
        if not obj or not obj.contract:
            return str(_("未关联合同"))

        try:
            binding = getattr(obj.contract, "folder_binding", None)
            if binding and binding.folder_path:
                return str(binding.folder_path)
            return str(_("未绑定文件夹"))
        except Exception:
            logger.exception("操作失败")
            return str(_("未绑定文件夹"))

    contract_folder_path_display.short_description = _("合同文件夹路径")  # type: ignore[attr-defined]

    def filing_number_display(self, obj: Case) -> str:
        if obj and obj.filing_number:
            return str(obj.filing_number)
        return str(_("未生成"))

    filing_number_display.short_description = _("建档编号")  # type: ignore[attr-defined]

    def has_folder_binding(self, obj: Case) -> str:
        try:
            if hasattr(obj, "folder_binding") and obj.folder_binding:
                return str(_("✓ 已绑定"))
            return str(_("未绑定"))
        except Exception:
            logger.exception("操作失败")
            return str(_("未绑定"))

    has_folder_binding.short_description = _("文件夹绑定")  # type: ignore[attr-defined]

    def get_matched_folder_templates_display(self, obj: Case) -> str:
        if not obj or not obj.case_type:
            return str(_("未设置案件类型"))
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        return str(service.get_matched_folder_templates(obj.case_type))

    get_matched_folder_templates_display.short_description = _("匹配的文件夹模板")  # type: ignore[attr-defined]


__all__: list[str] = ["CaseAdminViewsMixin"]
