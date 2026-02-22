"""Module for views."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog

logger = logging.getLogger("apps.cases")


def _log_inline_formset(inline_formset: Any, logger: logging.Logger) -> None:
    """记录 inline formset 的错误信息"""
    formset = inline_formset.formset
    for i, f in enumerate(formset.forms):
        if f.errors:
            logger.warning(f"[CaseAdmin.changeform_view] Inline {formset.prefix} form[{i}] errors: {f.errors}")
    logger.info(
        f"[CaseAdmin.changeform_view] Inline {formset.prefix} errors: "
        f"{formset.errors}, non_form_errors: {formset.non_form_errors()}"
    )
    logger.info(f"[CaseAdmin.changeform_view] Inline {formset.prefix} is_valid: {formset.is_valid()}")
    for nested in getattr(inline_formset, "inline_admin_formsets", []):
        nested_formset = nested.formset
        logger.info(f"[CaseAdmin.changeform_view] Nested {nested_formset.prefix} errors: {nested_formset.errors}")
        logger.info(f"[CaseAdmin.changeform_view] Nested {nested_formset.prefix} is_valid: {nested_formset.is_valid()}")
        for i, nf in enumerate(nested_formset.forms):
            if nf.errors:
                logger.warning(
                    f"[CaseAdmin.changeform_view] Nested {nested_formset.prefix} form[{i}] errors: {nf.errors}"
                )




class CaseAdminViewsMixin:
    def name_link(self, obj: Case) -> str:
        detail_url = reverse("admin:cases_case_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', detail_url, obj.name)

    name_link.short_description = _("案件名称")  # type: ignore[attr-defined]
    name_link.admin_order_field = "name"  # type: ignore[attr-defined]

    def get_urls(self) -> list[Any]:
        urls: list[Any] = super().get_urls()  # type: ignore[misc]
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
                "litigation-fee-calculator/",
                self.admin_site.admin_view(self.litigation_fee_calculator_view),  # type: ignore[attr-defined]
                name="cases_litigation_fee_calculator",
            ),
        ]
        return custom_urls + urls

    def litigation_fee_calculator_view(self, request: HttpRequest) -> HttpResponse:
        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "title": "诉讼费用计算器",
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
            else "未设置案件类型"
        )

        matched_case_file_templates, case_file_templates_missing_reason = self._get_case_file_templates(service, case)

        import json

        our_legal_entities_json, our_legal_entities = self._build_our_legal_entities(case, json)
        our_parties_json, our_parties = self._build_our_parties(case, json)
        respondents_json, respondents = self._build_respondents(case, json)

        case_materials_view = self._build_case_materials_view(request, case)

        template_binding_service = self._get_case_template_binding_service()  # type: ignore[attr-defined]
        bound_templates = template_binding_service.get_bindings_for_case(case.id)
        bound_templates_json = json.dumps(bound_templates, ensure_ascii=False)

        unified_templates = template_binding_service.get_unified_templates(case.id)
        unified_templates_json = json.dumps(unified_templates, ensure_ascii=False)

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
                "title": f"案件详情: {case.name}",
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_change_permission": self.has_change_permission(request, case),  # type: ignore[attr-defined]
                "matched_folder_templates": matched_folder_templates,
                "matched_case_file_templates": matched_case_file_templates,
                "case_file_templates_missing_reason": case_file_templates_missing_reason,
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

    def _get_case_file_templates(self, service: Any, case: Case) -> tuple[list[Any], str]:
        if not case.case_type:
            return [], "未设置案件类型"
        if not case.current_stage:
            return [], "未设置案件阶段"
        return service.get_matched_case_file_templates(case_type=case.case_type, case_stage=case.current_stage), ""

    @staticmethod
    def _build_our_legal_entities(case: Case, json: Any) -> tuple[str, list[dict[str, Any]]]:
        entities: list[dict[str, Any]] = [
            {"id": p.client.id, "name": p.client.name}
            for p in case.parties.all()
            if getattr(p.client, "is_our_client", False) and getattr(p.client, "client_type", "") == "legal"
        ]
        return json.dumps(entities, ensure_ascii=False), entities

    @staticmethod
    def _build_our_parties(case: Case, json: Any) -> tuple[str, list[dict[str, Any]]]:
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
    def _build_respondents(case: Case, json: Any) -> tuple[str, list[dict[str, Any]]]:
        respondents: list[dict[str, Any]] = [
            {"id": p.client.id, "name": p.client.name}
            for p in case.parties.all()
            if not getattr(p.client, "is_our_client", False)
        ]
        return json.dumps(respondents, ensure_ascii=False), respondents

    def _build_case_materials_view(self, request: HttpRequest, case: Case) -> Any:
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

        import json

        user = getattr(request, "user", None)
        law_firm_id = getattr(user, "law_firm_id", None) if user else None

        from apps.cases.models import CaseMaterial, CaseMaterialType

        used_type_ids = set(
            CaseMaterial.objects.filter(case_id=object_id, type_id__isnull=False).values_list("type_id", flat=True)
        )

        party_types_qs = CaseMaterialType.objects.filter(category="party", is_active=True).filter(
            models.Q(law_firm_id=law_firm_id) | models.Q(law_firm_id__isnull=True) | models.Q(id__in=used_type_ids)
        )
        party_types = list(party_types_qs.order_by("name").values("id", "name", "law_firm_id"))

        non_party_types_qs = CaseMaterialType.objects.filter(category="non_party", is_active=True).filter(
            models.Q(law_firm_id=law_firm_id) | models.Q(law_firm_id__isnull=True) | models.Q(id__in=used_type_ids)
        )
        non_party_types = list(non_party_types_qs.order_by("name").values("id", "name", "law_firm_id"))

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
                "title": f"上传/绑定材料: {case.name}",
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "detail_url": reverse("admin:cases_case_detail", args=[case.pk]),
                "party_types_json": json.dumps(party_types, ensure_ascii=False),
                "non_party_types_json": json.dumps(non_party_types, ensure_ascii=False),
                "our_case_parties_json": json.dumps(our_parties, ensure_ascii=False),
                "opponent_case_parties_json": json.dumps(opponent_parties, ensure_ascii=False),
                "supervising_authorities_json": json.dumps(authorities, ensure_ascii=False),
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
            return "无匹配的文件夹模板"
        return ""

    def _get_folder_disabled_reason_v2(self, matched_folder_templates: Any) -> str:
        if not matched_folder_templates or "无匹配" in matched_folder_templates:
            return "无匹配的文件夹模板"
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
            logger.info(f"[CaseAdmin.changeform_view] POST request, object_id={object_id}")

        response = super().changeform_view(request, object_id, form_url, extra_context)  # type: ignore[misc]

        if request.method == "POST":
            self._log_post_response(response, logger)

        return response  # type: ignore[no-any-return]

    @staticmethod
    def _log_post_response(response: HttpResponse, logger: logging.Logger) -> None:
        logger.info(f"[CaseAdmin.changeform_view] Response status: {response.status_code}")
        ctx = getattr(response, "context_data", None)
        if not ctx:
            return
        if "adminform" in ctx:
            form = ctx["adminform"].form
            logger.info(f"[CaseAdmin.changeform_view] Form errors: {form.errors}")
            logger.info(f"[CaseAdmin.changeform_view] Form is_valid: {not form.errors}")
        for inline_formset in ctx.get("inline_admin_formsets", []):
            _log_inline_formset(inline_formset, logger)

    def contract_folder_path_display(self, obj: Case) -> str:
        if not obj or not obj.contract:
            return "未关联合同"

        try:
            binding = getattr(obj.contract, "folder_binding", None)
            if binding and binding.folder_path:
                return str(binding.folder_path)
            return "未绑定文件夹"
        except Exception:
            logger.exception("操作失败")
            return "未绑定文件夹"

    contract_folder_path_display.short_description = _("合同文件夹路径")  # type: ignore[attr-defined]

    def filing_number_display(self, obj: Case) -> str:
        if obj and obj.filing_number:
            return str(obj.filing_number)
        return "未生成"

    filing_number_display.short_description = _("建档编号")  # type: ignore[attr-defined]

    def has_folder_binding(self, obj: Case) -> str:
        try:
            if hasattr(obj, "folder_binding") and obj.folder_binding:
                return "✓ 已绑定"
            return "未绑定"
        except Exception:
            logger.exception("操作失败")
            return "未绑定"

    has_folder_binding.short_description = _("文件夹绑定")  # type: ignore[attr-defined]

    def get_matched_folder_templates_display(self, obj: Case) -> str:
        if not obj or not obj.case_type:
            return "未设置案件类型"
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        return str(service.get_matched_folder_templates(obj.case_type))

    get_matched_folder_templates_display.short_description = _("匹配的文件夹模板")  # type: ignore[attr-defined]


__all__: list[str] = ["CaseAdminViewsMixin"]
