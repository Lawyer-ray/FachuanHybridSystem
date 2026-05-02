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
from apps.contracts.models.finalized_material import FinalizedMaterial

from .display_format_mixin import ContractDisplayFormatMixin, _get_contract_display_service

if TYPE_CHECKING:
    from django.db.models import Model

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


def _get_contract_detail_reminders(contract: Any) -> list[dict[str, Any]]:
    from apps.core.interfaces import ServiceLocator

    reminder_service = ServiceLocator.get_reminder_service()
    return reminder_service.export_contract_reminders_internal(contract_id=contract.id)


class ContractDisplayMixin(ContractDisplayFormatMixin):
    """合同 Admin 视图方法的 Mixin（继承显示方法）"""

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

    def generate_archive_docs_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """生成归档文件夹的 Admin view"""
        import json

        from django.http import JsonResponse

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            # 检查合同是否绑定了文件夹
            from apps.contracts.models.folder_binding import ContractFolderBinding

            try:
                binding = contract.folder_binding
            except ContractFolderBinding.DoesNotExist:
                binding = None

            if not binding or not binding.folder_path:
                return JsonResponse(
                    {"success": False, "error": str(_("请先在「文档与提醒」中绑定文件夹"))},
                    status=400,
                )

            from apps.contracts.services.archive import ArchiveGenerationService

            gen_service = ArchiveGenerationService()
            result = gen_service.generate_archive_folder(contract)

            if not result["success"]:
                return JsonResponse({"success": False, "error": result.get("error", "未知错误")}, status=500)

            generated_docs = result.get("generated_docs", [])
            errors = result.get("errors", [])

            if errors:
                logger.warning("归档文件夹部分生成失败: %s", "; ".join(errors))

            return JsonResponse({
                "success": True,
                "generated_docs": generated_docs,
                "archive_dir": result.get("archive_dir", ""),
                "errors": errors,
            })
        except Exception as e:
            logger.exception("生成归档文件夹失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def generate_single_archive_doc_view(self, request: HttpRequest, object_id: int, archive_item_code: str) -> HttpResponse:
        """生成单个归档文书的 Admin view"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive import ArchiveGenerationService

            gen_service = ArchiveGenerationService()
            result = gen_service.generate_single_archive_document(contract, archive_item_code)

            if result.get("error"):
                return JsonResponse({"success": False, "error": result["error"]})

            return JsonResponse({
                "success": True,
                "template_subtype": result.get("template_subtype"),
                "filename": result.get("filename"),
                "material_id": result.get("material_id"),
            })
        except Exception as e:
            logger.exception("生成单个归档文书失败: contract_id=%s, code=%s", object_id, archive_item_code)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def download_archive_item_view(self, request: HttpRequest, object_id: int, archive_item_code: str) -> HttpResponse:
        """下载归档检查项材料的 Admin view（多个文件自动合并为PDF）"""
        from django.http import HttpResponse as DjangoHttpResponse

        if not self.has_view_permission(request):
            raise PermissionDenied

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive import ArchiveGenerationService

            gen_service = ArchiveGenerationService()
            result = gen_service.download_archive_item(contract, archive_item_code)

            if result.get("error"):
                from django.http import JsonResponse
                return JsonResponse({"success": False, "error": result["error"]}, status=404)

            import urllib.parse

            response = DjangoHttpResponse(
                result["content"],
                content_type=result["content_type"],
            )
            encoded_filename = urllib.parse.quote(result["filename"].encode("utf-8"))
            # 预览模式：浏览器内显示（inline），否则下载（attachment）
            disposition = "inline" if request.GET.get("preview") == "1" else "attachment"
            response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded_filename}"
            return response
        except Exception as e:
            logger.exception("下载归档材料失败: contract_id=%s, code=%s", object_id, archive_item_code)
            from django.http import JsonResponse
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def detect_supervision_card_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """检测监督卡的 Admin view"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

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

    def sync_case_materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """从案件材料同步到归档的 Admin view"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            import json

            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            # 解析请求体，获取要同步的 archive_item_codes 和 case_ids（可选）
            codes: list[str] | None = None
            target_case_ids: list[int] | None = None
            try:
                body = json.loads(request.body) if request.body else {}
                codes = body.get("archive_item_codes")
                target_case_ids = body.get("case_ids")
            except (json.JSONDecodeError, ValueError):
                pass

            from apps.contracts.services.archive.wiring import build_archive_checklist_service

            checklist_service = build_archive_checklist_service()
            result = checklist_service.sync_case_materials_to_archive(contract, codes, target_case_ids)

            synced_count = len(result["synced"])
            error_count = len(result["errors"])

            if error_count:
                logger.warning(
                    "案件材料同步部分失败: contract_id=%s, errors=%d",
                    object_id,
                    error_count,
                )

            return JsonResponse({
                "success": synced_count > 0 or error_count == 0,
                "synced_count": synced_count,
                "skipped_count": len(result["skipped"]),
                "error_count": error_count,
                "details": result,
            })
        except Exception as e:
            logger.exception("同步案件材料失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def reset_and_resync_case_materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """重置并重新同步案件材料到归档的 Admin view

        先删除指定清单项下所有 case_material 类别的归档材料（含物理文件），
        然后重新从案件材料同步。手动上传/自动生成的材料不受影响。
        """
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            import json

            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            codes: list[str] | None = None
            try:
                body = json.loads(request.body) if request.body else {}
                codes = body.get("archive_item_codes")
            except (json.JSONDecodeError, ValueError):
                pass

            from apps.contracts.services.archive.wiring import build_archive_checklist_service

            checklist_service = build_archive_checklist_service()
            result = checklist_service.reset_and_resync_case_materials(contract, codes)

            sync_result = result["sync_result"]
            synced_count = len(sync_result["synced"])
            error_count = len(sync_result["errors"])

            return JsonResponse({
                "success": synced_count > 0 or error_count == 0,
                "deleted_count": result["deleted_count"],
                "synced_count": synced_count,
                "skipped_count": len(sync_result["skipped"]),
                "error_count": error_count,
                "details": sync_result,
            })
        except Exception as e:
            logger.exception("重置并重新同步案件材料失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def case_material_match_map_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """获取案件材料匹配映射的 Admin view"""
        from django.http import JsonResponse

        if not self.has_view_permission(request):
            raise PermissionDenied

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive.wiring import build_archive_checklist_service

            checklist_service = build_archive_checklist_service()
            result = checklist_service.get_case_material_match_map(contract)

            return JsonResponse({"success": True, "data": result})
        except Exception as e:
            logger.exception("获取案件材料匹配映射失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def toggle_compact_archive_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """切换精简视图状态的 Admin view"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            raise PermissionDenied

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)
            contract.compact_archive = not contract.compact_archive
            contract.save(update_fields=["compact_archive"])
            logger.info(
                "切换精简视图状态: contract_id=%s, compact_archive=%s",
                object_id,
                contract.compact_archive,
            )
            return JsonResponse({"success": True, "compact_archive": contract.compact_archive})
        except Exception as e:
            logger.exception("切换精简视图状态失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def scale_to_a4_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """按照A4裁切的 Admin view - 将非A4尺寸的PDF页面缩放为A4"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive import ArchiveGenerationService

            gen_service = ArchiveGenerationService()
            result = gen_service.scale_pages_to_a4(contract)

            return JsonResponse(result)
        except Exception as e:
            logger.exception("A4裁切失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def reorder_archive_materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """按归档清单项分组排序子项的 Admin view

        请求体格式：{"orders": {"lt_4": [3, 1, 2], "lt_7": [5, 4]}}
        key 为 archive_item_code，value 为 material_id 列表（按新顺序）。
        """
        import json

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            data = json.loads(request.body)
            orders: dict[str, list[int]] = data.get("orders", {})

            for code, material_ids in orders.items():
                for i, pk in enumerate(material_ids):
                    FinalizedMaterial.objects.filter(
                        pk=pk, contract_id=object_id, archive_item_code=code,
                    ).update(order=i)

            logger.info("归档材料排序已保存: contract_id=%s", object_id)
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("归档材料排序失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def move_archive_material_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """移动归档材料到另一个清单项的 Admin view

        请求体格式：{"material_id": 3, "target_code": "lt_7"}
        """
        import json

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            data = json.loads(request.body)
            material_id: int = data.get("material_id")
            target_code: str = data.get("target_code")

            if not material_id or not target_code:
                return JsonResponse({"success": False, "error": "参数不完整"}, status=400)

            material = FinalizedMaterial.objects.filter(
                pk=material_id, contract_id=object_id,
            ).first()

            if not material:
                return JsonResponse({"success": False, "error": "材料不存在"}, status=404)

            old_code = material.archive_item_code
            material.archive_item_code = target_code
            # 放到目标清单项末尾
            max_order = FinalizedMaterial.objects.filter(
                contract_id=object_id, archive_item_code=target_code,
            ).order_by("-order").values_list("order", flat=True).first() or 0
            material.order = (max_order or 0) + 1
            material.save(update_fields=["archive_item_code", "order"])

            logger.info(
                "归档材料已移动: material_id=%s, %s → %s, contract_id=%s",
                material_id, old_code, target_code, object_id,
            )
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("移动归档材料失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def preview_archive_material_view(self, request: HttpRequest, object_id: int, material_id: int) -> HttpResponse:
        """预览单个归档材料的 Admin view"""
        from django.http import HttpResponse as DjangoHttpResponse, JsonResponse

        if not self.has_view_permission(request):
            raise PermissionDenied

        try:
            material = FinalizedMaterial.objects.filter(
                pk=material_id, contract_id=object_id,
            ).first()

            if not material:
                return JsonResponse({"success": False, "error": "材料不存在"}, status=404)

            from pathlib import Path

            from django.conf import settings as django_settings

            file_path = Path(material.file_path)
            if not file_path.is_absolute():
                file_path = Path(django_settings.MEDIA_ROOT) / file_path

            if not file_path.exists():
                return JsonResponse({"success": False, "error": "文件不存在"}, status=404)

            content = file_path.read_bytes()
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                content_type = "application/pdf"
            elif suffix == ".docx":
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                content_type = "application/octet-stream"

            import urllib.parse

            response = DjangoHttpResponse(content, content_type=content_type)
            encoded_filename = urllib.parse.quote(material.original_filename.encode("utf-8"))
            response["Content-Disposition"] = f"inline; filename*=UTF-8''{encoded_filename}"
            return response
        except Exception as e:
            logger.exception("预览归档材料失败: material_id=%s", material_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def upload_archive_item_view(self, request: HttpRequest, object_id: int, archive_item_code: str) -> HttpResponse:
        """上传文件到归档检查清单项的 Admin view"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            uploaded_file = request.FILES.get("file")
            if not uploaded_file:
                return JsonResponse({"success": False, "error": "未选择文件"}, status=400)

            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

            from apps.contracts.services.archive.wiring import build_archive_checklist_service

            checklist_service = build_archive_checklist_service()
            material = checklist_service.upload_material_to_archive_item(
                contract=contract,
                archive_item_code=archive_item_code,
                uploaded_file=uploaded_file,
            )

            return JsonResponse({
                "success": True,
                "material_id": material.id,
                "original_filename": material.original_filename,
            })
        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except Exception as e:
            logger.exception("上传归档材料失败: contract_id=%s, code=%s", object_id, archive_item_code)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def delete_archive_material_view(self, request: HttpRequest, object_id: int, material_id: int) -> HttpResponse:
        """删除归档材料子项的 Admin view"""
        from pathlib import Path

        from django.conf import settings as django_settings
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            material = FinalizedMaterial.objects.filter(
                pk=material_id, contract_id=object_id,
            ).first()

            if not material:
                return JsonResponse({"success": False, "error": "材料不存在"}, status=404)

            # 删除物理文件
            if material.file_path:
                abs_file = Path(django_settings.MEDIA_ROOT) / material.file_path
                if not abs_file.is_absolute():
                    abs_file = Path(django_settings.MEDIA_ROOT) / material.file_path
                if abs_file.exists():
                    try:
                        abs_file.unlink()
                        logger.info("已删除归档文件: %s (material_id=%s)", material.file_path, material_id)
                    except OSError as e:
                        logger.warning("删除归档文件失败: %s: %s", material.file_path, e)

            material.delete()
            logger.info("已删除归档材料: material_id=%s, contract_id=%s", material_id, object_id)
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("删除归档材料失败: material_id=%s", material_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def clear_all_archive_materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """一键清空归档检查清单中的全部材料"""
        from pathlib import Path

        from django.conf import settings as django_settings
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            materials = FinalizedMaterial.objects.filter(contract_id=object_id)
            deleted_count = 0
            for material in materials:
                # 删除物理文件
                if material.file_path:
                    abs_file = Path(django_settings.MEDIA_ROOT) / material.file_path
                    if abs_file.exists():
                        try:
                            abs_file.unlink()
                        except OSError as e:
                            logger.warning("删除归档文件失败: %s: %s", material.file_path, e)
                material.delete()
                deleted_count += 1

            logger.info("已清空全部归档材料: contract_id=%s, count=%s", object_id, deleted_count)
            return JsonResponse({"success": True, "deleted_count": deleted_count})
        except Exception as e:
            logger.exception("清空归档材料失败: contract_id=%s", object_id)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

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
