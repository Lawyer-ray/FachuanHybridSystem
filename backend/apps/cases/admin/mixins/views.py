"""Module for views."""

from __future__ import annotations

import json as json_mod
import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog

if TYPE_CHECKING:
    from types import ModuleType

    from apps.cases.services.case.case_admin_service import CaseAdminService

logger = logging.getLogger("apps.cases")


def _log_inline_formset(inline_formset: Any, logger: logging.Logger) -> None:
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

        matched_folder_templates = (
            service.get_matched_folder_templates(case.case_type, our_legal_statuses)
            if case.case_type
            else str(_("未设置案件类型"))
        )

        matched_case_file_templates, case_file_templates_missing_reason = self._get_case_file_templates(service, case)

        grouped_case_file_templates = self._group_templates_by_sub_type(matched_case_file_templates)

        matched_folder_templates_list = (
            service.get_matched_folder_templates_list(case.case_type, our_legal_statuses) if case.case_type else []
        )

        our_legal_entities_json, our_legal_entities = self._build_our_legal_entities(case, json_mod)
        our_parties_json, our_parties = self._build_our_parties(case, json_mod)
        respondents_json, respondents = self._build_respondents(case, json_mod)

        case_materials_view = self._build_case_materials_view(request, case)

        template_binding_service = self._get_case_template_binding_service()  # type: ignore[attr-defined]
        bound_templates = template_binding_service.get_bindings_for_case(case.id)
        bound_templates_json = json_mod.dumps(bound_templates, ensure_ascii=False)

        unified_templates = template_binding_service.get_unified_templates(case.id)
        unified_templates_json = json_mod.dumps(unified_templates, ensure_ascii=False)

        has_preservation_template = any(
            t.get("function_code") == "preservation_application" or "财产保全申请书" in (t.get("name") or "")
            for t in unified_templates
        )
        has_delay_delivery_template = any(
            t.get("function_code") == "delay_delivery_application" or "暂缓送达申请书" in (t.get("name") or "")
            for t in unified_templates
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
            }
        )

        return render(request, "admin/cases/case/detail.html", context)

    def _get_case_file_templates(self, service: CaseAdminService, case: Case) -> tuple[list[dict[str, Any]], str]:
        if not case.case_type:
            return [], str(_("未设置案件类型"))
        if not case.current_stage:
            return [], str(_("未设置案件阶段"))
        return service.get_matched_case_file_templates(case_type=case.case_type, case_stage=case.current_stage), ""

    @staticmethod
    def _group_templates_by_sub_type(templates: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
        from apps.documents.models.choices import DocumentCaseFileSubType

        # 上面硬编码区域已覆盖的 sub_type，自动排除
        HARDCODED_SUB_TYPES = {"power_of_attorney_materials", "property_preservation_materials"}

        label_map = dict(DocumentCaseFileSubType.choices)
        groups: dict[str, list[dict[str, Any]]] = {}
        for t in templates:
            sub = t.get("case_sub_type", "other_materials")
            if sub in HARDCODED_SUB_TYPES:
                continue
            groups.setdefault(sub, []).append(t)
        order = [c[0] for c in DocumentCaseFileSubType.choices]
        return [(label_map.get(k, k), v) for k in order if (v := groups.get(k))]

    @staticmethod
    def _build_our_legal_entities(case: Case, json: ModuleType) -> tuple[str, list[dict[str, Any]]]:
        entities: list[dict[str, Any]] = [
            {"id": p.client.id, "name": p.client.name}
            for p in case.parties.all()
            if getattr(p.client, "is_our_client", False) and getattr(p.client, "client_type", "") == "legal"
        ]
        return json.dumps(entities, ensure_ascii=False), entities

    @staticmethod
    def _build_our_parties(case: Case, json: ModuleType) -> tuple[str, list[dict[str, Any]]]:
        parties: list[dict[str, Any]] = []
        for party in case.parties.all():
            client = party.client
            if not getattr(client, "is_our_client", False):
                continue
            parties.append(
                {
                    "id": client.id,
                    "name": client.name,
                    "client_type": getattr(client, "client_type", "") or "",
                    "legal_status": getattr(party, "legal_status", None),
                    "legal_status_display": (
                        getattr(party, "get_legal_status_display", lambda: "")()
                        if getattr(party, "legal_status", None)
                        else ""
                    ),
                }
            )
        return json.dumps(parties, ensure_ascii=False), parties

    @staticmethod
    def _build_respondents(case: Case, json: ModuleType) -> tuple[str, list[dict[str, Any]]]:
        respondents: list[dict[str, Any]] = [
            {"id": p.client.id, "name": p.client.name}
            for p in case.parties.all()
            if not getattr(p.client, "is_our_client", False)
        ]
        return json.dumps(respondents, ensure_ascii=False), respondents

    def _build_case_materials_view(self, request: HttpRequest, case: Case) -> dict[str, Any]:
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
        used_type_ids = material_service.get_used_type_ids(case_id=object_id)

        party_types = material_service.get_material_types_by_category(
            category="party",
            law_firm_id=law_firm_id,
            used_type_ids=used_type_ids,
        )
        non_party_types = material_service.get_material_types_by_category(
            category="non_party",
            law_firm_id=law_firm_id,
            used_type_ids=used_type_ids,
        )

        our_parties: list[dict[str, Any]] = []
        opponent_parties: list[dict[str, Any]] = []
        for party in case.parties.all():
            client = party.client
            item: dict[str, Any] = {
                "id": party.id,
                "name": getattr(client, "name", "") or "",
                "legal_status": getattr(party, "legal_status", None),
                "legal_status_display": (
                    getattr(party, "get_legal_status_display", lambda: "")()
                    if getattr(party, "legal_status", None)
                    else ""
                ),
            }
            if getattr(client, "is_our_client", False):
                our_parties.append(item)
            else:
                opponent_parties.append(item)

        authorities: list[dict[str, Any]] = []
        for auth in case.supervising_authorities.all().order_by("created_at"):
            authorities.append(
                {
                    "id": auth.id,
                    "name": auth.name or "",
                    "authority_type": auth.authority_type or "",
                    "authority_type_display": auth.get_authority_type_display() if auth.authority_type else "",
                }
            )

        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": _("上传/绑定材料: %(name)s") % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "detail_url": reverse("admin:cases_case_detail", args=[case.pk]),
                "party_types_json": json_mod.dumps(party_types, ensure_ascii=False),
                "non_party_types_json": json_mod.dumps(non_party_types, ensure_ascii=False),
                "our_case_parties_json": json_mod.dumps(our_parties, ensure_ascii=False),
                "opponent_case_parties_json": json_mod.dumps(opponent_parties, ensure_ascii=False),
                "supervising_authorities_json": json_mod.dumps(authorities, ensure_ascii=False),
            }
        )

        return render(request, "admin/cases/case/materials.html", context)

    def _get_case_with_relations(self, case_id: int) -> Case | None:
        from django.db.models import Prefetch

        try:
            return (  # type: ignore[no-any-return]
                Case.objects.select_related(
                    "contract",
                    "folder_binding",
                )
                .prefetch_related(
                    "case_numbers",
                    "supervising_authorities",
                    "parties__client",
                    "assignments__lawyer",
                    Prefetch(
                        "logs",
                        queryset=CaseLog.objects.select_related("actor")
                        .prefetch_related("attachments", "reminders")
                        .order_by("-created_at"),
                    ),
                    "chats",
                )
                .get(pk=case_id)
            )
        except Case.DoesNotExist:
            return None

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
        extra_context: dict[str, Any] | None = None,
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
