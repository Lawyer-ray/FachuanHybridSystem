"""Module for views."""

from __future__ import annotations

import json as json_mod
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
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
    """案件管理后台视图Mixin，提供自定义URL和视图方法"""

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
                "casenumber/upload-temp/",
                self.admin_site.admin_view(self.upload_temp_document_view),  # type: ignore[attr-defined]
                name="cases_casenumber_upload_temp",
            ),
            path(
                "<int:object_id>/open-folder/",
                self.admin_site.admin_view(self.open_folder_view),
                name="cases_case_open_folder",
            ),
            path(
                "<int:object_id>/email-folder-import/",
                self.admin_site.admin_view(self.email_folder_import_view),
                name="cases_case_email_folder_import",
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
        return material_service.get_case_materials_view(  # type: ignore[no-any-return]
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

    def parse_document_view(self, request: HttpRequest, casenumber_id: int) -> HttpResponse:
        """解析裁判文书，提取案号、文书名称、执行依据主文"""
        from django.contrib import messages
        from django.http import JsonResponse

        from apps.cases.models import CaseNumber
        from apps.core.exceptions import BusinessException

        try:
            # 支持临时文件路径（未保存的情况）
            # 前端以 application/json 发送，需从 request.body 解析
            import json

            temp_file_path = None
            if request.body:
                try:
                    body = json.loads(request.body)
                    temp_file_path = body.get("temp_file_path")
                except (json.JSONDecodeError, ValueError):
                    pass
            if not temp_file_path:
                temp_file_path = request.POST.get("temp_file_path")

            if temp_file_path:
                # 临时文件模式（未保存到数据库）
                from pathlib import Path

                file_path = temp_file_path
                if not Path(file_path).exists():
                    return JsonResponse({"success": False, "error": "临时文件不存在，请重新上传"}, status=400)
            else:
                # 已保存的文件模式
                case_number = CaseNumber.objects.get(pk=casenumber_id)
                if not case_number.document_file:
                    return JsonResponse({"success": False, "error": "请先上传裁判文书文件"}, status=400)
                file_path = case_number.document_file.path

            # 调用解析服务
            from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

            extractor = JudgmentPdfExtractor()
            extraction_result = extractor.extract(file_path)

            # 如果是已保存的文件，更新所有字段
            if not temp_file_path:
                if extraction_result.number:
                    case_number.number = extraction_result.number
                if extraction_result.document_name:
                    case_number.document_name = extraction_result.document_name
                if extraction_result.content:
                    case_number.document_content = extraction_result.content
                case_number.save(update_fields=["number", "document_name", "document_content"])
                logger.info("成功解析裁判文书: case_number_id=%s", casenumber_id)
            else:
                logger.info("成功解析临时文件: %s", file_path)

            return JsonResponse(
                {
                    "success": True,
                    "number": extraction_result.number,
                    "document_name": extraction_result.document_name,
                    "content": extraction_result.content,
                }
            )

        except CaseNumber.DoesNotExist:
            return JsonResponse({"success": False, "error": "案号记录不存在"}, status=404)
        except BusinessException as e:
            logger.warning("解析裁判文书业务异常: case_number_id=%s, error=%s", casenumber_id, str(e))
            return JsonResponse({"success": False, "error": str(e.message)}, status=400)
        except Exception as e:
            logger.exception("解析裁判文书失败: case_number_id=%s", casenumber_id)
            return JsonResponse({"success": False, "error": f"解析失败: {e}"}, status=500)

    def parse_execution_request_view(self, request: HttpRequest, casenumber_id: int) -> HttpResponse:
        """解析执行依据主文并生成申请执行事项预览（规则引擎）"""
        from django.http import JsonResponse

        from apps.cases.models import CaseNumber
        from apps.documents.services.placeholders.litigation.execution_request_service import ExecutionRequestService

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "仅支持 POST 请求"}, status=405)

        try:
            body: dict[str, object] = {}
            if request.body:
                import json

                body = json.loads(request.body.decode("utf-8"))

            case_number = CaseNumber.objects.select_related("case").get(pk=casenumber_id)

            cutoff_date = self._coerce_optional_date(body.get("cutoff_date"))
            paid_amount = self._coerce_optional_decimal(body.get("paid_amount"))
            use_deduction_order = self._coerce_optional_bool(body.get("use_deduction_order"))
            year_days = self._coerce_optional_int(body.get("year_days"))
            date_inclusion = self._coerce_optional_str(body.get("date_inclusion"))
            enable_llm_fallback = self._coerce_optional_bool(body.get("enable_llm_fallback"))

            service = ExecutionRequestService()
            result = service.preview_for_case_number(
                case=case_number.case,
                case_number=case_number,
                cutoff_date=cutoff_date,
                paid_amount=paid_amount,
                use_deduction_order=use_deduction_order,
                year_days=year_days,
                date_inclusion=date_inclusion,
                enable_llm_fallback=enable_llm_fallback,
            )

            return JsonResponse(
                {
                    "success": True,
                    "preview_text": result["preview_text"],
                    "structured_params": result["structured_params"],
                    "warnings": result["warnings"],
                }
            )
        except CaseNumber.DoesNotExist:
            return JsonResponse({"success": False, "error": "案号记录不存在"}, status=404)
        except Exception as e:
            logger.exception("解析申请执行事项失败: case_number_id=%s", casenumber_id)
            return JsonResponse({"success": False, "error": f"解析失败: {e}"}, status=500)

    def parse_document_view_no_id(self, request: HttpRequest) -> HttpResponse:
        """解析裁判文书（无需caseNumberId，用于临时文件）"""
        from django.http import JsonResponse

        from apps.core.exceptions import BusinessException

        try:
            import json

            body = json.loads(request.body)
            temp_file_path = body.get("temp_file_path")

            if not temp_file_path:
                return JsonResponse({"success": False, "error": "缺少临时文件路径"}, status=400)

            from pathlib import Path

            file_path = temp_file_path
            if not Path(file_path).exists():
                return JsonResponse({"success": False, "error": "临时文件不存在，请重新上传"}, status=400)

            # 调用解析服务
            from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

            extractor = JudgmentPdfExtractor()
            extraction_result = extractor.extract(file_path)

            logger.info("成功解析临时文件: %s", file_path)

            return JsonResponse(
                {
                    "success": True,
                    "number": extraction_result.number,
                    "document_name": extraction_result.document_name,
                    "content": extraction_result.content,
                }
            )

        except BusinessException as e:
            logger.warning("解析裁判文书业务异常: error=%s", str(e))
            return JsonResponse({"success": False, "error": str(e.message)}, status=400)
        except Exception as e:
            logger.exception("解析裁判文书失败")
            return JsonResponse({"success": False, "error": f"解析失败: {e}"}, status=500)

    def upload_temp_document_view(self, request: HttpRequest) -> HttpResponse:
        """上传裁判文书到临时目录"""
        import os
        import uuid
        from pathlib import Path

        from django.conf import settings
        from django.http import JsonResponse

        try:
            if request.method != "POST":
                return JsonResponse({"success": False, "error": "仅支持 POST 请求"}, status=405)

            file = request.FILES.get("file")
            if not file:
                return JsonResponse({"success": False, "error": "未上传文件"}, status=400)

            # 验证文件类型
            ext = os.path.splitext(file.name or "")[1].lower()
            if ext not in [".pdf"]:
                return JsonResponse({"success": False, "error": "仅支持 PDF 格式"}, status=400)

            # 创建临时目录
            temp_dir = Path(settings.MEDIA_ROOT) / "case_documents" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 生成唯一文件名
            temp_filename = f"{uuid.uuid4().hex}_{file.name}"
            temp_path = temp_dir / temp_filename

            # 保存文件
            with open(temp_path, "wb+") as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            logger.info("临时文件上传成功: %s", temp_path)

            return JsonResponse(
                {
                    "success": True,
                    "temp_file_path": str(temp_path),
                    "temp_file_name": file.name,
                }
            )

        except Exception as e:
            logger.exception("临时文件上传失败")
            return JsonResponse({"success": False, "error": f"上传失败: {e}"}, status=500)

    def open_folder_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """打开案件绑定的本地文件夹（Finder/资源管理器）"""
        import platform
        import subprocess
        from pathlib import Path

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_view_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            from apps.cases.models.material import CaseFolderBinding

            try:
                binding = CaseFolderBinding.objects.get(case_id=object_id)
            except CaseFolderBinding.DoesNotExist:
                return JsonResponse({"success": False, "error": str(_("未绑定文件夹"))}, status=404)

            folder_path = binding.folder_path
            if not folder_path:
                return JsonResponse({"success": False, "error": str(_("文件夹路径为空"))}, status=400)

            folder = Path(folder_path).expanduser()
            if not folder.exists():
                return JsonResponse(
                    {"success": False, "error": str(_("文件夹不存在: %(path)s") % {"path": folder_path})}, status=404
                )

            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", str(folder)])  # noqa: S607
            elif system == "Windows":
                subprocess.Popen(["explorer", str(folder)])  # noqa: S607
            else:
                subprocess.Popen(["xdg-open", str(folder)])  # noqa: S607

            logger.info("已打开案件文件夹: %s, case_id=%s", folder_path, object_id)
            return JsonResponse({"success": True, "folder_path": folder_path})
        except Exception as e:
            logger.exception("打开案件文件夹失败: case_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def email_folder_import_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """从案件绑定文件夹的'邮件往来'子目录批量导入案件日志"""
        import json as json_mod

        from django.http import JsonResponse

        if not self.has_view_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            from apps.cases.models.material import CaseFolderBinding

            binding = CaseFolderBinding.objects.filter(case_id=object_id).first()
            if not binding or not binding.folder_path:
                return JsonResponse({"success": False, "error": str(_("未绑定文件夹"))}, status=404)

            if request.method == "GET":
                # 列出可用的子文件夹（含"邮件往来"关键词的）
                from pathlib import Path

                root = Path(binding.folder_path).expanduser().resolve()
                if not root.exists():
                    return JsonResponse({"success": False, "error": str(_("文件夹不存在"))}, status=404)

                email_subfolders = []
                for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    if "邮件" in child.name or "mail" in child.name.lower() or "email" in child.name.lower():
                        email_subfolders.append({
                            "relative_path": child.name,
                            "display_name": child.name,
                        })

                return JsonResponse({"success": True, "subfolders": email_subfolders})

            if request.method == "POST":
                # 执行导入
                body = json_mod.loads(request.body) if request.body else {}
                subfolder = body.get("subfolder", "")
                if not subfolder:
                    return JsonResponse({"success": False, "error": str(_("请指定子文件夹"))}, status=400)

                from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService

                service = EmailFolderScanService()
                result = service.import_email_folder(
                    case_id=object_id,
                    subfolder=subfolder,
                    user=getattr(request, "user", None),
                    org_access=getattr(request, "org_access", None),
                    perm_open_access=getattr(request, "perm_open_access", False),
                )

                log_count = len(result["logs"])
                skipped = result["skipped_count"]
                msg = str(_("导入完成：新增 %(count)s 条日志，跳过 %(skipped)s 条（已存在）")) % {
                    "count": log_count,
                    "skipped": skipped,
                }
                logger.info("案件 %s 邮件导入完成: 新增=%s, 跳过=%s", object_id, log_count, skipped)
                return JsonResponse({"success": True, "message": msg, "imported_count": log_count, "skipped_count": skipped})

            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        except Exception as e:
            logger.exception("邮件文件夹导入失败: case_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def _coerce_optional_date(self, raw: object) -> date | None:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _coerce_optional_decimal(self, raw: object) -> Decimal | None:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _coerce_optional_bool(raw: object) -> bool | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return raw
        value = str(raw).strip().lower()
        if not value:
            return None
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        return None

    @staticmethod
    def _coerce_optional_int(raw: object) -> int | None:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _coerce_optional_str(raw: object) -> str | None:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        return value


__all__: list[str] = ["CaseAdminViewsMixin"]
