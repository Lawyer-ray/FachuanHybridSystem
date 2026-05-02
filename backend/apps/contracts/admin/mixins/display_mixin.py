"""
Contract Admin - Display Mixin

详情页视图、URL 路由等视图方法.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import URLPattern, path, reverse
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException, NotFoundError

from .archive_mixin import ContractArchiveMixin, _get_contract_admin_service
from .display_format_mixin import ContractDisplayFormatMixin, _get_contract_display_service

if TYPE_CHECKING:
    from django.db.models import Model

logger = logging.getLogger("apps.contracts")


def _get_contract_detail_reminders(contract: Any) -> list[dict[str, Any]]:
    from apps.core.interfaces import ServiceLocator

    reminder_service = ServiceLocator.get_reminder_service()
    return reminder_service.export_contract_reminders_internal(contract_id=contract.id)


class ContractDisplayMixin(ContractArchiveMixin, ContractDisplayFormatMixin):
    """合同 Admin 视图方法的 Mixin（继承归档和显示方法）"""

    if TYPE_CHECKING:
        admin_site: Any
        model: type[Model]

        def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...
        def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...

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
                "<int:object_id>/generate-archive-doc/<str:archive_item_code>/",
                self.admin_site.admin_view(self.generate_single_archive_doc_view),
                name="contracts_contract_generate_single_archive_doc",
            ),
            path(
                "<int:object_id>/download-archive-item/<str:archive_item_code>/",
                self.admin_site.admin_view(self.download_archive_item_view),
                name="contracts_contract_download_archive_item",
            ),
            path(
                "<int:object_id>/detect-supervision-card/",
                self.admin_site.admin_view(self.detect_supervision_card_view),
                name="contracts_contract_detect_supervision_card",
            ),
            path(
                "<int:object_id>/sync-case-materials/",
                self.admin_site.admin_view(self.sync_case_materials_view),
                name="contracts_contract_sync_case_materials",
            ),
            path(
                "<int:object_id>/reset-and-resync-case-materials/",
                self.admin_site.admin_view(self.reset_and_resync_case_materials_view),
                name="contracts_contract_reset_and_resync_case_materials",
            ),
            path(
                "<int:object_id>/case-material-match-map/",
                self.admin_site.admin_view(self.case_material_match_map_view),
                name="contracts_contract_case_material_match_map",
            ),
            path(
                "<int:object_id>/toggle-compact-archive/",
                self.admin_site.admin_view(self.toggle_compact_archive_view),
                name="contracts_contract_toggle_compact_archive",
            ),
            path(
                "<int:object_id>/scale-to-a4/",
                self.admin_site.admin_view(self.scale_to_a4_view),
                name="contracts_contract_scale_to_a4",
            ),
            path(
                "<int:object_id>/reorder-archive-materials/",
                self.admin_site.admin_view(self.reorder_archive_materials_view),
                name="contracts_contract_reorder_archive_materials",
            ),
            path(
                "<int:object_id>/move-archive-material/",
                self.admin_site.admin_view(self.move_archive_material_view),
                name="contracts_contract_move_archive_material",
            ),
            path(
                "<int:object_id>/preview-archive-material/<int:material_id>/",
                self.admin_site.admin_view(self.preview_archive_material_view),
                name="contracts_contract_preview_archive_material",
            ),
            path(
                "<int:object_id>/upload-archive-item/<str:archive_item_code>/",
                self.admin_site.admin_view(self.upload_archive_item_view),
                name="contracts_contract_upload_archive_item",
            ),
            path(
                "<int:object_id>/delete-archive-material/<int:material_id>/",
                self.admin_site.admin_view(self.delete_archive_material_view),
                name="contracts_contract_delete_archive_material",
            ),
            path(
                "<int:object_id>/clear-all-archive-materials/",
                self.admin_site.admin_view(self.clear_all_archive_materials_view),
                name="contracts_contract_clear_all_archive_materials",
            ),
            path(
                "<int:object_id>/open-folder/",
                self.admin_site.admin_view(self.open_folder_view),
                name="contracts_contract_open_folder",
            ),
            path(
                "<int:object_id>/tab/<str:tab_name>/",
                self.admin_site.admin_view(self.tab_lazy_load_view),
                name="contracts_contract_tab_lazy_load",
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

        # 检查合同文件夹路径是否可达，必要时通过 inode 自动修复
        folder_path_auto_repaired = False
        folder_binding = getattr(contract, "folder_binding", None)
        if folder_binding:
            from apps.contracts.admin.wiring_admin import get_contract_folder_binding_service

            folder_service = get_contract_folder_binding_service()
            _is_accessible, folder_path_auto_repaired = folder_service.check_and_repair_path(folder_binding)

        # 构建上下文
        context = self.admin_site.each_context(request)
        # 从 session 读取列表页筛选参数，供"返回列表"链接使用
        changelist_qs = request.session.get("contract_changelist_filters", "")
        changelist_filter_querystring = f"?{changelist_qs}" if changelist_qs else ""
        context.update(
            {
                "contract": contract,
                "title": _("合同详情: %(name)s") % {"name": contract.name},
                "opts": self.model._meta,
                "has_change_permission": self.has_change_permission(request, contract),
                "has_view_permission": self.has_view_permission(request, contract),
                "changelist_filter_querystring": changelist_filter_querystring,
                # 传递模板需要的额外数据
                "primary_lawyer": self._get_primary_lawyer_obj(contract),
                "contract_parties": contract.contract_parties.all(),
                "assignments": contract.assignments.all(),
                "payments": ctx_data["payments"],
                "total_payment_amount": ctx_data["total_payment_amount"],
                "reminders": _get_contract_detail_reminders(contract),
                "supplementary_agreements": ctx_data["supplementary_agreements"],
                "folder_binding": getattr(contract, "folder_binding", None),
                "folder_path_auto_repaired": folder_path_auto_repaired,
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
                "archive_code_to_template": ctx_data.get("archive_code_to_template", {}),
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

    def open_folder_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """打开合同绑定的本地文件夹（Finder/资源管理器）"""
        import platform
        import subprocess
        from pathlib import Path

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_view_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            from apps.contracts.models.folder_binding import ContractFolderBinding

            try:
                binding = ContractFolderBinding.objects.get(contract_id=object_id)
            except ContractFolderBinding.DoesNotExist:
                return JsonResponse({"success": False, "error": str(_("未绑定文件夹"))}, status=404)

            folder_path = binding.folder_path
            if not folder_path:
                return JsonResponse({"success": False, "error": str(_("文件夹路径为空"))}, status=400)

            folder = Path(folder_path).expanduser()
            if not folder.exists():
                return JsonResponse({"success": False, "error": str(_("文件夹不存在: %(path)s") % {"path": folder_path})}, status=404)

            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", str(folder)])  # noqa: S607
            elif system == "Windows":
                subprocess.Popen(["explorer", str(folder)])  # noqa: S607
            else:
                subprocess.Popen(["xdg-open", str(folder)])  # noqa: S607

            logger.info("已打开文件夹: %s, contract_id=%s", folder_path, object_id)
            return JsonResponse({"success": True, "folder_path": folder_path})
        except Exception as e:
            logger.exception("打开文件夹失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def tab_lazy_load_view(self, request: HttpRequest, object_id: int, tab_name: str) -> HttpResponse:
        """Tab 懒加载视图 - 首次切换时 AJAX 获取重内容 Tab"""
        from django.template.loader import render_to_string

        if not self.has_view_permission(request):
            raise PermissionDenied

        valid_tabs = {"documents", "finalized"}
        if tab_name not in valid_tabs:
            return HttpResponse("无效的标签页", status=400)

        admin_service = _get_contract_admin_service()
        try:
            contract = admin_service.query_service.get_contract_detail(object_id)
        except NotFoundError:
            raise Http404(_("合同不存在")) from None

        ctx_data = admin_service.get_contract_detail_context(contract.id)

        template_map = {
            "documents": "admin/contracts/contract/partials/documents.html",
            "finalized": "admin/contracts/contract/partials/finalized_materials.html",
        }

        # 构建模板上下文
        context = {
            "contract": contract,
            "opts": self.model._meta,
            "has_change_permission": self.has_change_permission(request, contract),
            "has_view_permission": self.has_view_permission(request, contract),
            "primary_lawyer": self._get_primary_lawyer_obj(contract),
            "reminders": _get_contract_detail_reminders(contract),
            "supplementary_agreements": ctx_data["supplementary_agreements"],
            "folder_binding": getattr(contract, "folder_binding", None),
            "has_contract_template": ctx_data["has_contract_template"],
            "has_folder_template": ctx_data["has_folder_template"],
            "contract_template_display": ctx_data.get("contract_template_display", ""),
            "folder_template_display": ctx_data.get("folder_template_display", ""),
            "contract_templates_list": ctx_data.get("contract_templates_list", []),
            "folder_templates_list": ctx_data.get("folder_templates_list", []),
            "has_supplementary_agreements": ctx_data["has_supplementary_agreements"],
            "related_cases": ctx_data["related_cases"],
            "finalized_materials": ctx_data["finalized_materials"],
            "finalized_materials_grouped": ctx_data["finalized_materials_grouped"],
            "archive_checklist": ctx_data.get("archive_checklist", {}),
            "archive_code_to_template": ctx_data.get("archive_code_to_template", {}),
            "media_url": getattr(__import__("django.conf", fromlist=["settings"]).settings, "MEDIA_URL", "/media/"),
            "today": ctx_data["today"],
            "soon_due_date": ctx_data["soon_due_date"],
        }

        html = render_to_string(template_map[tab_name], context, request=request)
        return HttpResponse(html)
