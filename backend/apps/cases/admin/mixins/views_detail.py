"""案件 Admin 详情页、材料页与 changeform 扩展。"""

from __future__ import annotations

import json as json_mod
import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse

from apps.cases.models import Case
from apps.core.models.enums import CaseStage, ContactRole

if TYPE_CHECKING:
    from apps.cases.services.case.case_admin_service import CaseAdminService

logger = logging.getLogger("apps.cases")


def _get_contact_role_choices() -> list[tuple[str, str]]:
    return [(str(k), str(v)) for k, v in ContactRole.choices]


def _get_case_stage_choices() -> list[tuple[str, str]]:
    return [(str(k), str(v)) for k, v in CaseStage.choices]


def _has_court_filing_plugin() -> bool:
    try:
        from plugins import has_court_automation_plugin  # type: ignore[attr-defined]

        return has_court_automation_plugin()  # type: ignore[no-any-return]
    except ImportError:
        return False


def _get_case_sync_integration() -> Any:
    """取「一张网案件同步」插件的 admin 集成层；插件未安装时返回 None。

    一张网（登录、协议、字段解析、落库）全部由 plugins 承载，宿主只拿一个
    钩子对象：追加 URL、注入模板上下文。插件缺失时案件编辑页退化为原样。
    """
    try:
        from plugins.court_automation.case_sync import admin_integration

        return admin_integration
    except ImportError:
        return None


def _get_media_url() -> str:
    from django.conf import settings

    return str(getattr(settings, "MEDIA_URL", "/media/"))


def _log_inline_formset(inline_formset: object, logger: logging.Logger) -> None:
    """记录 inline formset 的错误信息（仅记录有错误的表单）"""
    formset = getattr(inline_formset, "formset", None)
    if formset is None:
        return
    for i, f in enumerate(formset.forms):
        if f.errors:
            logger.warning(
                "[CaseAdmin.changeform_view] Inline %s form[%s] errors: %s",
                formset.prefix,
                i,
                f.errors,
            )
    non_form = formset.non_form_errors()
    if non_form:
        logger.warning(
            "[CaseAdmin.changeform_view] Inline %s non_form_errors: %s",
            formset.prefix,
            non_form,
        )


class CaseAdminDetailViewsMixin:  # pragma: no cover
    """案件详情页、材料页、changeform 扩展与自定义 URL 注册。"""

    def get_urls(self) -> list[URLPattern]:  # pragma: no cover
        # 直接调用admin.ModelAdmin.get_urls，避免Mixin继承链问题
        # Mixin没有定义get_urls时super()会找不到方法
        from django.contrib.admin import ModelAdmin

        urls = ModelAdmin.get_urls(self)  # type: ignore[arg-type]
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
            path(
                "casenumber/<int:casenumber_id>/parse-document/",
                self.admin_site.admin_view(self.parse_document_view),  # type: ignore[attr-defined]
                name="cases_casenumber_parse_document",
            ),
            path(
                "casenumber/<int:casenumber_id>/parse-execution-request/",
                self.admin_site.admin_view(self.parse_execution_request_view),  # type: ignore[attr-defined]
                name="cases_casenumber_parse_execution_request",
            ),
            path(
                "casenumber/parse-document/",
                self.admin_site.admin_view(self.parse_document_view_no_id),  # type: ignore[attr-defined]
                name="cases_casenumber_parse_document_no_id",
            ),
            path(
                "llm-models/",
                self.admin_site.admin_view(self.llm_models_view),  # type: ignore[attr-defined]
                name="cases_casenumber_llm_models",
            ),
            path(
                "casenumber/upload-temp/",
                self.admin_site.admin_view(self.upload_temp_document_view),  # type: ignore[attr-defined]
                name="cases_casenumber_upload_temp",
            ),
            path(
                "<int:object_id>/open-folder/",
                self.admin_site.admin_view(self.open_folder_view),  # type: ignore[attr-defined]
                name="cases_case_open_folder",
            ),
            path(
                "<int:object_id>/email-folder-import/",
                self.admin_site.admin_view(self.email_folder_import_view),  # type: ignore[attr-defined]
                name="cases_case_email_folder_import",
            ),
        ]
        # 「一张网同步」端点由插件提供（协议/登录/落库都在 plugins 内）
        case_sync = _get_case_sync_integration()
        if case_sync is not None and case_sync.is_available():
            custom_urls.extend(case_sync.get_urls(self))
        return custom_urls + urls

    def _ensure_case_access(self, request: HttpRequest, case: Case | None, *, case_id: int | None = None) -> None:
        """行级权限校验：复用 CaseAccessPolicy.ensure_access_ctx，无权访问时抛 PermissionDenied（admin 渲染 403）。

        解耦（2026-10-19）：业务异常 → django PermissionDenied 的转换收敛到
        core.security.admin_access.ensure_admin_object_access 泛型，本方法保留
        原签名与 Http404 兜底，调用方零改动。
        """
        from apps.cases.services.case.case_access_policy import CaseAccessPolicy
        from apps.core.security.admin_access import ensure_admin_object_access

        target_case_id = case.pk if case is not None else case_id
        if target_case_id is None:
            raise Http404("案件不存在")
        ensure_admin_object_access(
            request,
            CaseAccessPolicy(),
            object_id=int(target_case_id),
            message="无权限访问此案件",
            id_kwarg="case_id",
            obj=case,
            obj_kwarg="case",
        )

    def mock_trial_view(self, request: HttpRequest, object_id: int) -> HttpResponse:  # pragma: no cover
        case = self._get_case_with_relations(object_id)
        if case is None:
            raise Http404("案件不存在")
        if not self.has_view_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied
        self._ensure_case_access(request, case)
        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": "模拟庭审: %(name)s" % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
            }
        )
        return render(request, "litigation_ai/mock_trial.html", context)

    def litigation_fee_calculator_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "title": "诉讼费用计算器",
                "opts": self.model._meta,  # type: ignore[attr-defined]
            }
        )
        return render(request, "admin/cases/litigation_fee_calculator.html", context)

    def detail_view(self, request: HttpRequest, object_id: int) -> HttpResponse:  # pragma: no cover
        case = self._get_case_with_relations(object_id)

        if case is None:
            raise Http404("案件不存在")

        if not self.has_view_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied

        self._ensure_case_access(request, case)

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
            else "未设置案件类型"
        )

        matched_case_file_templates, case_file_templates_missing_reason = service.get_case_file_templates_for_detail(
            case
        )
        case_file_sub_type_choices = service.get_case_file_sub_type_choices()

        grouped_case_file_templates = service.group_templates_by_sub_type(
            matched_case_file_templates,
            case_file_sub_type_choices,
        )
        grouped_case_file_templates_for_display = service.group_templates_by_sub_type(
            matched_case_file_templates,
            case_file_sub_type_choices,
            exclude_special_sub_types=False,
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

        # 案件链（前序/后代）查询已下沉 service
        from apps.cases.services.case.case_chain_service import get_case_chain

        # 安全审计（2026-10-19）：链上案件按当前用户行级口径过滤，无权访问的前序/后代案件从链上隐藏
        related_chain = get_case_chain(
            case,
            user=request.user,
            org_access=getattr(request, "org_access", None),
            perm_open_access=getattr(request, "perm_open_access", False),
        )

        # 检查案件文件夹路径可达性，先修复合同路径再检查案件路径
        folder_path_auto_repaired = False
        case_folder_binding = getattr(case, "folder_binding", None)
        if case_folder_binding:
            case_folder_service = self._get_case_folder_binding_service()  # type: ignore[attr-defined]
            folder_path_auto_repaired = case_folder_service.check_and_repair_contract_path(case_folder_binding)

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
                "title": "案件详情: %(name)s" % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_change_permission": self.has_change_permission(request, case),  # type: ignore[attr-defined]
                "matched_folder_templates": matched_folder_templates,
                "matched_case_file_templates": matched_case_file_templates,
                "matched_folder_templates_list": matched_folder_templates_list,
                "case_file_templates_missing_reason": case_file_templates_missing_reason,
                "grouped_case_file_templates": grouped_case_file_templates,
                "grouped_case_file_templates_for_display": grouped_case_file_templates_for_display,
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
                "has_court_filing_plugin": _has_court_filing_plugin(),
                "folder_path_auto_repaired": folder_path_auto_repaired,
                "contacts": list(case.contacts.all()),
                "contact_role_choices": list(_get_contact_role_choices()),
                "case_stage_choices": list(_get_case_stage_choices()),
                "related_cases": related_chain if len(related_chain) > 1 else [],
                "media_url": _get_media_url(),
            }
        )

        return render(request, "admin/cases/case/detail.html", context)

    def _build_case_materials_view(self, request: HttpRequest, case: Case) -> dict[str, object]:  # pragma: no cover
        material_service = self._get_case_material_service()  # type: ignore[attr-defined]
        return material_service.get_case_materials_view(  # type: ignore[no-any-return]
            case_id=case.id,
            user=getattr(request, "user", None),
            org_access=getattr(request, "org_access", None),
            perm_open_access=getattr(request, "perm_open_access", False),
        )

    def materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:  # pragma: no cover
        case = self._get_case_with_relations(object_id)
        if case is None:
            raise Http404("案件不存在")

        if not self.has_change_permission(request, case):  # type: ignore[attr-defined]
            raise PermissionDenied

        self._ensure_case_access(request, case)

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
        default_category = (request.GET.get("category") or "").strip()
        if default_category not in {"party", "non_party"}:
            default_category = ""

        context = self.admin_site.each_context(request)  # type: ignore[attr-defined]
        context.update(
            {
                "case": case,
                "title": "上传/绑定材料: %(name)s" % {"name": case.name},
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "detail_url": reverse("admin:cases_case_detail", args=[case.pk]),
                "party_types_json": json_mod.dumps(payload["party_types"], ensure_ascii=False),
                "non_party_types_json": json_mod.dumps(payload["non_party_types"], ensure_ascii=False),
                "our_case_parties_json": json_mod.dumps(payload["our_parties"], ensure_ascii=False),
                "opponent_case_parties_json": json_mod.dumps(payload["opponent_parties"], ensure_ascii=False),
                "supervising_authorities_json": json_mod.dumps(payload["authorities"], ensure_ascii=False),
                "scan_session_id": scan_session_id,
                "open_scan": open_scan,
                "default_category": default_category,
            }
        )

        return render(request, "admin/cases/case/materials.html", context)

    def _get_case_with_relations(self, case_id: int) -> Case | None:  # pragma: no cover
        service = self._get_case_admin_service()  # type: ignore[attr-defined]
        return service.get_case_with_admin_relations(case_id)  # type: ignore[no-any-return]

    def _get_folder_disabled_reason_v2(self, matched_folder_templates: str) -> str:  # pragma: no cover
        if not matched_folder_templates or "无匹配" in matched_folder_templates:
            return "无匹配的文件夹模板"
        return ""

    def changeform_view(  # pragma: no cover
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        if request.method == "POST":
            logger.info("[CaseAdmin.changeform_view] POST request, object_id=%s", object_id)

        if object_id:
            has_binding = self._check_folder_binding(int(object_id))
            if extra_context is None:
                extra_context = {}
            extra_context["has_folder_binding"] = has_binding
            extra_context.update(self._build_case_sync_context(int(object_id)))

        response = super().changeform_view(request, object_id, form_url, extra_context)  # type: ignore[misc]

        if request.method == "POST":
            self._log_post_response(response)

        return response  # type: ignore[no-any-return]

    def _build_case_sync_context(self, case_id: int) -> dict[str, object]:  # pragma: no cover
        """「一张网ID + 同步」区块的模板上下文（全部来自插件）。"""
        case_sync = _get_case_sync_integration()
        if case_sync is None or not case_sync.is_available():
            return {"has_yizhangwang_plugin": False, "yizhangwang_case_space_url": ""}

        case = Case.objects.filter(pk=case_id).only("id", "yz_wid").first()
        context = case_sync.get_context(case)
        return dict(context)

    @staticmethod
    def _check_folder_binding(case_id: int) -> bool:  # pragma: no cover
        """检查案件或其关联合同是否绑定了文件夹（单条查询）。"""
        from django.db.models import Q

        return (
            Case.objects.filter(pk=case_id)
            .filter(Q(folder_binding__isnull=False) | Q(contract__isnull=False, contract__folder_binding__isnull=False))
            .exists()
        )

    @staticmethod
    def _log_post_response(response: HttpResponse) -> None:  # pragma: no cover
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


__all__: list[str] = ["CaseAdminDetailViewsMixin"]
