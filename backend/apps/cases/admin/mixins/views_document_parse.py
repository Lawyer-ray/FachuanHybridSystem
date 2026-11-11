"""案件 Admin 的裁判文书解析、执行事项预览与临时上传视图。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from apps.cases.models import Case

from .views_coercion import (
    _coerce_optional_bool,
    _coerce_optional_date,
    _coerce_optional_decimal,
    _coerce_optional_int,
    _coerce_optional_str,
)

logger = logging.getLogger("apps.cases")


def _resolve_confined_temp_path(temp_file_path: str) -> Path | None:
    """把请求传入的临时文件路径约束在 MEDIA_ROOT/case_documents/temp 之下。

    上传接口现在返回相对 MEDIA_ROOT 的路径（安全审计：不暴露服务器绝对路径），
    相对路径先拼到 MEDIA_ROOT 下再 resolve()；历史调用方传绝对路径的仍兼容。
    必须用 resolve() 后 is_relative_to 判断，不能用字符串前缀。
    路径越界时返回 None，由调用方拒绝。
    """
    from django.conf import settings

    media_root = Path(settings.MEDIA_ROOT).resolve()
    allowed_dir = media_root / "case_documents" / "temp"
    raw = Path(temp_file_path)
    file_path = (media_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if not file_path.is_relative_to(allowed_dir):
        return None
    return file_path


class CaseAdminDocumentParseMixin:  # pragma: no cover
    """裁判文书解析与执行事项预览相关视图。"""

    if TYPE_CHECKING:
        # 由聚合入口 CaseAdminViewsMixin 的其他 mixin / ModelAdmin 提供
        def _ensure_case_access(
            self, request: HttpRequest, case: Case | None, *, case_id: int | None = None
        ) -> None: ...  # pragma: no cover

        def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool: ...  # pragma: no cover

    def parse_document_view(self, request: HttpRequest, casenumber_id: int) -> HttpResponse:  # pragma: no cover
        """解析裁判文书，提取案号、文书名称、执行依据主文"""
        from django.contrib import messages
        from django.http import JsonResponse

        from apps.cases.models import CaseNumber
        from apps.core.exceptions import BusinessException

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "仅支持 POST 请求"}, status=405)

        if not self.has_change_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": "无权限"}, status=403)

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
                # 临时文件模式（未保存到数据库）；路径必须约束在
                # MEDIA_ROOT/case_documents/temp 下，防止任意文件读取
                file_path_obj = _resolve_confined_temp_path(str(temp_file_path))
                if file_path_obj is None:
                    return JsonResponse({"success": False, "error": "非法文件路径"}, status=400)
                if not file_path_obj.exists():
                    return JsonResponse({"success": False, "error": "临时文件不存在，请重新上传"}, status=400)
                file_path = str(file_path_obj)
            else:
                # 已保存的文件模式
                case_number = CaseNumber.objects.get(pk=casenumber_id)
                self._ensure_case_access(request, case_number.case)
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
        except PermissionDenied:
            raise
        except BusinessException as e:
            logger.warning("解析裁判文书业务异常: case_number_id=%s, error=%s", casenumber_id, str(e))
            return JsonResponse({"success": False, "error": str(e.message)}, status=400)
        except Exception:
            logger.exception("解析裁判文书失败: case_number_id=%s", casenumber_id)
            return JsonResponse({"success": False, "error": "解析失败，请查看服务器日志"}, status=500)

    def parse_execution_request_view(
        self, request: HttpRequest, casenumber_id: int
    ) -> HttpResponse:  # pragma: no cover
        """解析执行依据主文并生成申请执行事项预览（规则引擎）"""
        from django.http import JsonResponse

        from apps.cases.models import CaseNumber
        from apps.documents.services.placeholders.litigation.execution_request_service import ExecutionRequestService

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "仅支持 POST 请求"}, status=405)

        if not self.has_change_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": "无权限"}, status=403)

        try:
            body: dict[str, object] = {}
            if request.body:
                import json

                body = json.loads(request.body.decode("utf-8"))

            case_number = CaseNumber.objects.select_related("case").get(pk=casenumber_id)
            self._ensure_case_access(request, case_number.case)

            cutoff_date = _coerce_optional_date(body.get("cutoff_date"))
            paid_amount = _coerce_optional_decimal(body.get("paid_amount"))
            use_deduction_order = _coerce_optional_bool(body.get("use_deduction_order"))
            year_days = _coerce_optional_int(body.get("year_days"))
            date_inclusion = _coerce_optional_str(body.get("date_inclusion"))
            enable_llm_fallback = _coerce_optional_bool(body.get("enable_llm_fallback"))
            llm_model = _coerce_optional_str(body.get("llm_model"))

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
                llm_model=llm_model,
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
        except PermissionDenied:
            raise
        except Exception:
            logger.exception("解析申请执行事项失败: case_number_id=%s", casenumber_id)
            return JsonResponse({"success": False, "error": "解析失败，请查看服务器日志"}, status=500)

    def llm_models_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """返回当前可用的 LLM 模型列表（供执行事项解析下拉框使用）。

        复用 ModelListService：返回其合并 SystemConfig / LLMProvider 后的模型列表；
        is_fallback 仅表示远端 API 基线不可用，此时仍会返回本地配置的模型。
        """
        from django.http import JsonResponse

        from apps.core.llm.model_list_service import ModelListService

        try:
            result = ModelListService().get_result()
            # result.models 已包含 SystemConfig / LLMProvider 合并后的模型；
            # is_fallback 仅表示远端 API 基线不可用，不代表模型列表不可用，
            # 因此这里不能因 is_fallback 而清空列表（否则下拉框永远为空）。
            models = result.models
            return JsonResponse(
                {
                    "success": True,
                    "models": [
                        {
                            "id": str(m.get("id", "")),
                            "name": str(m.get("name", "")),
                            "context_window": int(m.get("context_window", 0) or 0),
                        }
                        for m in models
                    ],
                    "is_fallback": result.is_fallback,
                    "error_message": result.error_message,
                }
            )
        except Exception:
            logger.exception("获取 LLM 模型列表失败")
            return JsonResponse(
                {"success": False, "error": "获取模型列表失败，请查看服务器日志", "models": [], "is_fallback": True},
                status=500,
            )

    def parse_document_view_no_id(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """解析裁判文书（无需caseNumberId，用于临时文件）"""
        from django.http import JsonResponse

        from apps.core.exceptions import BusinessException

        try:
            import json

            body = json.loads(request.body)
            temp_file_path = body.get("temp_file_path")

            if not temp_file_path:
                return JsonResponse({"success": False, "error": "缺少临时文件路径"}, status=400)

            # 防止 path traversal：解析路径必须在 MEDIA_ROOT/case_documents/temp 下
            file_path = _resolve_confined_temp_path(str(temp_file_path))
            if file_path is None:
                return JsonResponse({"success": False, "error": "非法文件路径"}, status=400)

            if not file_path.exists():
                return JsonResponse({"success": False, "error": "临时文件不存在，请重新上传"}, status=400)

            # 调用解析服务
            from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

            extractor = JudgmentPdfExtractor()
            extraction_result = extractor.extract(str(file_path))

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
        except Exception:
            logger.exception("解析裁判文书失败")
            return JsonResponse({"success": False, "error": "解析失败，请查看服务器日志"}, status=500)

    def upload_temp_document_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """上传裁判文书到临时目录"""
        import os
        import uuid
        from pathlib import Path

        from django.conf import settings
        from django.core.files.storage import default_storage
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

            # 防止 path traversal：只保留文件名部分
            safe_name = Path(str(file.name or "")).name
            temp_filename = f"{uuid.uuid4().hex}_{safe_name}"
            rel_path = f"case_documents/temp/{temp_filename}"

            # 保存文件；返回相对 MEDIA_ROOT 的路径（安全审计：不暴露服务器绝对路径）
            saved_name = default_storage.save(rel_path, file)

            logger.info("临时文件上传成功: %s", saved_name)

            return JsonResponse(
                {
                    "success": True,
                    "temp_file_path": saved_name,
                    "temp_file_name": file.name,
                }
            )

        except Exception:
            logger.exception("临时文件上传失败")
            return JsonResponse({"success": False, "error": "上传失败，请查看服务器日志"}, status=500)


__all__: list[str] = ["CaseAdminDocumentParseMixin"]
