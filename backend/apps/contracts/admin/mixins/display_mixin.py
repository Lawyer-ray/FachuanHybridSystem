"""
Contract Admin - Display Mixin

显示相关的方法:详情页视图、字段显示等.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException, NotFoundError

if TYPE_CHECKING:
    from django.contrib.admin import ModelAdmin
    from django.db.models import Model

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


def _get_contract_display_service() -> Any:
    """工厂函数获取合同显示服务"""
    from apps.contracts.admin.wiring_admin import get_contract_display_service

    return get_contract_display_service()


def _get_contract_detail_reminders(contract: Any) -> list[dict[str, Any]]:
    from apps.core.interfaces import ServiceLocator

    reminder_service = ServiceLocator.get_reminder_service()
    return reminder_service.export_contract_reminders_internal(contract_id=contract.id)


class ContractDisplayMixin:
    """合同 Admin 显示相关方法的 Mixin"""

    if TYPE_CHECKING:
        admin_site: Any
        model: type[Model]

        def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...
        def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...

    @admin.display(description=_("合同名称"), ordering="name")
    def name_link(self, obj: Any) -> Any:
        """生成指向详情页的合同名称链接"""
        url = reverse("admin:contracts_contract_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.name)

    @admin.display(description=_("主办律师"))
    def get_primary_lawyer(self, obj: Any) -> Any:
        """显示主办律师（使用 prefetch_related 数据避免 N+1）"""
        for assignment in obj.assignments.all():
            if assignment.is_primary:
                lawyer = assignment.lawyer
                return lawyer.real_name or lawyer.username
        return "-"

    def _get_primary_lawyer_obj(self, obj: Any) -> Any:
        """返回主办律师对象（供详情页模板使用）"""
        for assignment in obj.assignments.all():
            if assignment.is_primary:
                return assignment.lawyer
        return None

    @admin.display(description=_("主办律师"))
    def get_primary_lawyer_display(self, obj: Any) -> Any:
        """详情页显示主办律师(只读)"""
        from apps.contracts.admin.wiring_admin import get_contract_assignment_query_service

        service = get_contract_assignment_query_service()
        assignment = service.get_primary_lawyer(obj.pk)
        if assignment:
            lawyer = assignment.lawyer
            name = lawyer.real_name or lawyer.username
            return f"{name} (ID: {lawyer.id})"
        return _("无")

    @admin.display(description=_("律所OA链接"))
    def law_firm_oa_link_display(self, obj: Any) -> Any:
        """显示合同所属律所的 OA 登录链接（可点击）。"""
        from apps.oa_filing.services.script_executor_service import SUPPORTED_SITES
        from apps.organization.models import AccountCredential

        law_firm_ids: list[int] = []
        seen: set[int] = set()
        for assignment in obj.assignments.select_related("lawyer").all():
            lawyer = getattr(assignment, "lawyer", None)
            law_firm_id = getattr(lawyer, "law_firm_id", None)
            if not law_firm_id or law_firm_id in seen:
                continue
            seen.add(int(law_firm_id))
            law_firm_ids.append(int(law_firm_id))

        if not law_firm_ids:
            return _("未配置")

        credential = (
            AccountCredential.objects.filter(
                lawyer__law_firm_id__in=law_firm_ids,
                site_name__in=SUPPORTED_SITES,
            )
            .exclude(url__isnull=True)
            .exclude(url="")
            .order_by("id")
            .first()
        )

        if not credential:
            return _("未配置")

        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
            credential.url,
            _("打开OA系统"),
        )

    @admin.display(description=_("建档编号"))
    def filing_number_display(self, obj: Any) -> Any:
        """显示建档编号(只读)

        如果合同已有建档编号,显示编号;否则显示"未生成".

        Requirements: 1.1, 1.2, 3.1
        """
        if obj and obj.filing_number:
            return obj.filing_number
        return _("未生成")

    @admin.display(description=_("匹配的合同模板"))
    def get_matched_template_display(self, obj: Any) -> Any:
        """显示匹配的合同模板

        Requirements: 1.4
        """
        if not obj or not obj.pk:
            return _("请先保存合同")

        try:
            display_service = _get_contract_display_service()
            return display_service.get_matched_document_template(obj)
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("获取合同 %s 匹配模板失败: %s", obj.id, e, exc_info=True)
            return _("查询失败")

    @admin.display(description=_("匹配的文件夹模板"))
    def get_matched_folder_templates_display(self, obj: Any) -> Any:
        """显示匹配的文件夹模板

        Requirements: 7.1
        """
        if not obj or not obj.pk:
            return _("请先保存合同")

        try:
            display_service = _get_contract_display_service()
            return display_service.get_matched_folder_templates(obj)
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("获取合同 %s 匹配文件夹模板失败: %s", obj.id, e, exc_info=True)
            return _("查询失败")

    def get_urls(self) -> Any:
        """添加自定义 URL 路由"""
        urls: list[URLPattern] = super().get_urls()  # type: ignore[misc]
        custom_urls = [
            path(
                "<int:object_id>/detail/",
                self.admin_site.admin_view(self.detail_view),
                name="contracts_contract_detail",
            ),
            path(
                "<int:object_id>/generate-archive-docs/",
                self.admin_site.admin_view(self.generate_archive_docs_view),
                name="contracts_contract_generate_archive_docs",
            ),
            path(
                "<int:object_id>/detect-supervision-card/",
                self.admin_site.admin_view(self.detect_supervision_card_view),
                name="contracts_contract_detect_supervision_card",
            ),
            path(
                "<int:object_id>/confirm-archive/",
                self.admin_site.admin_view(self.confirm_archive_view),
                name="contracts_contract_confirm_archive",
            ),
        ]
        return custom_urls + urls

    def detail_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """合同详情页视图"""
        # 权限检查
        if not self.has_view_permission(request):
            raise PermissionDenied

        # 获取合同对象,优化查询
        admin_service = _get_contract_admin_service()
        try:
            contract = admin_service.query_service.get_contract_detail(object_id)
        except NotFoundError:
            raise Http404(_("合同不存在")) from None

        # 判断是否显示代理阶段(仅民商事/刑事/行政/劳动仲裁类型显示)
        ctx_data = admin_service.get_contract_detail_context(contract.id)

        # 构建上下文
        context = self.admin_site.each_context(request)
        context.update(
            {
                "contract": contract,
                "title": _("合同详情: %(name)s") % {"name": contract.name},
                "opts": self.model._meta,
                "has_change_permission": self.has_change_permission(request, contract),
                "has_view_permission": self.has_view_permission(request, contract),
                # 传递模板需要的额外数据
                "primary_lawyer": self._get_primary_lawyer_obj(contract),
                "contract_parties": contract.contract_parties.all(),
                "assignments": contract.assignments.all(),
                "payments": ctx_data["payments"],
                "total_payment_amount": ctx_data["total_payment_amount"],
                "reminders": _get_contract_detail_reminders(contract),
                "supplementary_agreements": ctx_data["supplementary_agreements"],
                "folder_binding": getattr(contract, "folder_binding", None),
                "show_representation_stages": ctx_data["show_representation_stages"],
                "representation_stages_display": ctx_data["representation_stages_display"],
                "today": ctx_data["today"],
                "soon_due_date": ctx_data["soon_due_date"],
                "has_contract_template": ctx_data["has_contract_template"],
                "has_folder_template": ctx_data["has_folder_template"],
                "contract_template_display": ctx_data.get("contract_template_display", ""),
                "folder_template_display": ctx_data.get("folder_template_display", ""),
                "contract_templates_list": ctx_data.get("contract_templates_list", []),
                "folder_templates_list": ctx_data.get("folder_templates_list", []),
                "has_supplementary_agreements": ctx_data["has_supplementary_agreements"],
                "payment_progress": ctx_data["payment_progress"],
                "invoice_summary": ctx_data["invoice_summary"],
                "related_cases": ctx_data["related_cases"],
                "finalized_materials": ctx_data["finalized_materials"],
                "finalized_materials_grouped": ctx_data["finalized_materials_grouped"],
                "invoices_by_payment": ctx_data["invoices_by_payment"],
                "client_payments": ctx_data["client_payments"],
                "total_client_payment": ctx_data["total_client_payment"],
                "archive_checklist": ctx_data.get("archive_checklist", {}),
                "media_url": getattr(__import__("django.conf", fromlist=["settings"]).settings, "MEDIA_URL", "/media/"),
            }
        )

        return render(request, "admin/contracts/contract/detail.html", context)

    def _check_contract_template(self, contract: Any) -> Any:
        """
        检查是否有匹配的合同模板

        使用 ContractDisplayService 检查模板,避免直接导入 documents 模块.
        添加错误处理,确保在查询失败时返回 False.

        Requirements: 1.4, 6.2
        """
        try:
            display_service = _get_contract_display_service()
            result = display_service.get_matched_document_template(contract)
            return result not in ["无匹配模板", "查询失败"]
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("检查合同 %s 的文书模板失败: %s", contract.id, e, exc_info=True)
            return False

    def _check_folder_template(self, contract: Any) -> Any:
        """
        检查是否有匹配的文件夹模板

        使用 ContractDisplayService 检查模板,避免直接导入 documents 模块.
        添加错误处理,确保在查询失败时返回 False.

        Requirements: 1.4, 6.2
        """
        try:
            display_service = _get_contract_display_service()
            result = display_service.get_matched_folder_templates(contract)
            return result not in ["无匹配模板", "查询失败"]
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("检查合同 %s 的文件夹模板失败: %s", contract.id, e, exc_info=True)
            return False

    def generate_archive_docs_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """生成归档文书的 Admin view"""
        import json

        from django.http import JsonResponse

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive import ArchiveGenerationService

            gen_service = ArchiveGenerationService()
            results = gen_service.generate_archive_documents(contract)

            generated_count = sum(1 for r in results if r.get("error") is None)
            errors = [r for r in results if r.get("error")]

            if errors:
                error_msgs = "; ".join(f"{r.get('template_subtype', '?')}: {r['error']}" for r in errors)
                logger.warning("归档文书部分生成失败: %s", error_msgs)

            return JsonResponse({
                "success": True,
                "generated_count": generated_count,
                "total_count": len(results),
                "errors": [{"subtype": r.get("template_subtype"), "error": r["error"]} for r in errors],
            })
        except Exception as e:
            logger.exception("生成归档文书失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def detect_supervision_card_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """自动检测监督卡的 Admin view"""
        from django.http import JsonResponse

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive import SupervisionCardExtractor

            extractor = SupervisionCardExtractor()
            result = extractor.detect_and_extract(contract)

            return JsonResponse({
                "success": True,
                "found": result["found"],
                "page_number": result.get("page_number"),
                "material_id": result.get("material_id"),
                "error": result.get("error"),
            })
        except Exception as e:
            logger.exception("检测监督卡失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "found": False, "error": str(e)}, status=500)

    def confirm_archive_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """确认归档的 Admin view - 校验必需项完成度后流转状态"""
        from django.http import JsonResponse

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            from apps.contracts.models import ContractStatus

            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            if contract.status != ContractStatus.CLOSED:
                return JsonResponse({"success": False, "error": str(_("只有已结案合同才能确认归档"))}, status=400)

            # 校验必需项完成度
            from apps.contracts.services.archive import ArchiveChecklistService

            checklist_service = ArchiveChecklistService()
            checklist = checklist_service.get_checklist_with_status(contract)

            if checklist["required_completed_count"] < checklist["required_total_count"]:
                missing = [
                    item["name"]
                    for item in checklist["items"]
                    if item["required"] and not item["completed"]
                ]
                return JsonResponse({
                    "success": False,
                    "error": str(_("必需项未完成: %(items)s") % {"items": "、".join(missing[:5])}),
                    "required_completed": checklist["required_completed_count"],
                    "required_total": checklist["required_total_count"],
                }, status=400)

            contract.status = ContractStatus.ARCHIVED
            contract.save(update_fields=["status"])

            logger.info(
                "合同 %s 已确认归档",
                contract.pk,
                extra={"contract_id": contract.pk, "action": "confirm_archive"},
            )
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("确认归档失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)
