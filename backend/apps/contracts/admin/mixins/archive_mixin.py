"""
Contract Admin - Archive Mixin

归档相关视图方法：生成归档文书、下载、监督卡检测、案件材料同步、材料管理等。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _

from apps.contracts.models.finalized_material import FinalizedMaterial

if TYPE_CHECKING:
    from django.db.models import Model

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


class ContractArchiveMixin:
    """归档相关 Admin 视图的 Mixin"""

    if TYPE_CHECKING:
        admin_site: Any
        model: type[Model]

        def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...
        def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...

    # ── 归档文书生成 ──

    def generate_archive_docs_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """生成归档文件夹的 Admin view"""
        import json

        from django.http import JsonResponse

        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "error": str(_("无权限"))}, status=403)

        try:
            admin_service = _get_contract_admin_service()
            contract = admin_service.query_service.get_contract_detail(object_id)

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

    # ── 归档下载与预览 ──

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
            disposition = "inline" if request.GET.get("preview") == "1" else "attachment"
            response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded_filename}"
            return response
        except Exception as e:
            logger.exception("下载归档材料失败: contract_id=%s, code=%s", object_id, archive_item_code)
            from django.http import JsonResponse
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

    # ── 监督卡检测 ──

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

    # ── 案件材料同步 ──

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
        """重置并重新同步案件材料到归档的 Admin view"""
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

    # ── 归档设置 ──

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
        """按照A4裁切的 Admin view"""
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

    # ── 归档材料管理 ──

    def reorder_archive_materials_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """按归档清单项分组排序子项的 Admin view"""
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
        """移动归档材料到另一个清单项的 Admin view"""
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

            if material.file_path:
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
