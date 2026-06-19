"""文书模板 Admin 自定义视图 Mixin。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from apps.core.interfaces import ServiceLocator
from apps.documents.storage import (
    PRIVATE_DOCX_ROOT_SETTING,
    get_configured_private_docx_templates_root,
    get_docx_templates_root,
    get_docx_templates_source,
)

logger = logging.getLogger(__name__)


def _get_admin_service() -> Any:
    """工厂函数获取Admin服务"""
    from apps.documents.services.template.document_template.admin_service import DocumentTemplateAdminService

    return DocumentTemplateAdminService()


def _to_django_relative_path(path: Path) -> str:
    """将绝对路径尽量转换为相对 Django 服务目录（backend）的路径。"""
    from django.conf import settings

    backend_root = Path(str(getattr(settings, "BASE_DIR", "."))).resolve().parent
    target = path.resolve()
    try:
        return target.relative_to(backend_root).as_posix()
    except ValueError:
        return Path(str(target)).as_posix()


def _normalize_private_docx_root(raw_value: str) -> str:
    """标准化私有模板根目录输入（支持绝对路径或相对 backend 路径）。"""
    from django.conf import settings

    normalized = raw_value.strip()
    if not normalized:
        return ""

    candidate = Path(normalized).expanduser()
    if not candidate.is_absolute():
        backend_root = Path(str(getattr(settings, "BASE_DIR", "."))).resolve().parent
        candidate = (backend_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists() or not candidate.is_dir():
        raise ValueError("模板根目录不存在或不是文件夹")

    return str(candidate)


def _get_system_config_service() -> Any:
    return ServiceLocator.get_system_config_service()


class TemplateAdminViewsMixin:
    """文书模板 Admin 自定义视图 Mixin，包含所有 URL 路由和视图方法。"""

    def get_urls(self) -> list[Any]:  # pragma: no cover
        """添加自定义URL"""
        from django.urls import path

        urls = super().get_urls()  # type: ignore[misc]
        custom_urls = [
            path(
                "<int:pk>/download/",
                self.admin_site.admin_view(self.download_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_download",
            ),
            path(
                "initialize-defaults/",
                self.admin_site.admin_view(self.initialize_defaults_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_initialize",
            ),
            path(
                "set-docx-root/",
                self.admin_site.admin_view(self.set_docx_root_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_set_docx_root",
            ),
            path(
                "extract-placeholders/",
                self.admin_site.admin_view(self.extract_placeholders_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_extract_placeholders",
            ),
            path(
                "smart-fill-preview/",
                self.admin_site.admin_view(self.smart_fill_preview_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_smart_fill_preview",
            ),
            path(
                "smart-fill-render/",
                self.admin_site.admin_view(self.smart_fill_render_view),  # type: ignore[attr-defined]
                name="documents_documenttemplate_smart_fill_render",
            ),
        ]
        return custom_urls + urls  # type: ignore[no-any-return]

    def _resolve_template_path(self, request: Any) -> tuple[str | None, str | None]:  # pragma: no cover
        """从三种文件来源解析模板绝对路径。

        Returns:
            (path, error): path 为文件绝对路径（上传文件为临时路径，调用方负责清理），
                          error 为错误信息（成功时为 None）。
        """
        import tempfile

        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            suffix = Path(str(uploaded_file.name)).suffix or ".docx"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                return tmp.name, None

        existing_file = request.POST.get("existing_file", "").strip()
        file_path = request.POST.get("file_path", "").strip()
        template_path = existing_file or file_path
        if template_path:
            from apps.documents.storage import resolve_docx_template_path

            resolved = resolve_docx_template_path(template_path)
            if resolved.exists():
                return str(resolved), None
            return None, f"文件不存在: {template_path}"

        return None, "请提供 file、existing_file 或 file_path 参数"

    def extract_placeholders_view(self, request: Any) -> Any:  # pragma: no cover
        """从上传的文件或已有模板文件中提取占位符，返回 JSON。"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"error": "仅支持 POST 请求"}, status=405)

        tmp_path: str | None = None
        try:
            template_path, err = self._resolve_template_path(request)
            if err or not template_path:
                return JsonResponse({"error": err or "模板路径为空"}, status=400 if "请提供" in (err or "") else 404)

            # 上传文件时 template_path 是临时路径，需要在 finally 中清理
            if request.FILES.get("file"):
                tmp_path = template_path

            from apps.documents.services.document_template.placeholder_extractor import (
                extract_placeholders as extract_from_file,
            )

            placeholders = extract_from_file(template_path)

            from apps.documents.models import Placeholder

            defined_keys = set(Placeholder.objects.filter(is_active=True).values_list("key", flat=True))
            result = [{"key": p, "defined": p in defined_keys} for p in placeholders]

            source_label = (
                "上传文件"
                if tmp_path
                else f"模板文件: {request.POST.get('existing_file') or request.POST.get('file_path')}"
            )
            return JsonResponse({"placeholders": result, "source": source_label, "count": len(result)})

        except Exception as e:
            logger.exception("提取占位符失败")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def smart_fill_preview_view(self, request: Any) -> Any:  # pragma: no cover
        """AI 智能填充预览：调用 LLM 生成占位符映射，返回 JSON。"""
        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"error": "仅支持 POST 请求"}, status=405)

        user_input = request.POST.get("user_input", "").strip()
        if not user_input:
            return JsonResponse({"error": "请输入自然语言描述"}, status=400)

        llm_model = request.POST.get("llm_model", "").strip() or None

        tmp_path: str | None = None
        try:
            template_path, err = self._resolve_template_path(request)
            if err:
                return JsonResponse({"error": err}, status=400 if "请提供" in err else 404)

            if request.FILES.get("file"):
                tmp_path = template_path

            from apps.documents.services.infrastructure.wiring import get_smart_fill_service

            service = get_smart_fill_service()
            result = service.preview(template_path, user_input, model=llm_model)

            if result.error:
                return JsonResponse({"error": result.error}, status=400)

            return JsonResponse(
                {"placeholders": [{"key": p.key, "value": p.value, "source": p.source} for p in result.placeholders]}
            )

        except Exception as e:
            logger.exception("智能填充预览失败")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def smart_fill_render_view(self, request: Any) -> Any:  # pragma: no cover
        """AI 智能填充渲染：根据用户编辑后的映射值渲染 docx 并返回下载。"""
        from django.http import HttpResponse, JsonResponse

        if request.method != "POST":
            return JsonResponse({"error": "仅支持 POST 请求"}, status=405)

        placeholders_json = request.POST.get("placeholders", "[]")
        try:
            placeholders_data = json.loads(placeholders_json)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的占位符数据"}, status=400)

        tmp_path: str | None = None
        try:
            template_path, err = self._resolve_template_path(request)
            if err:
                return JsonResponse({"error": err}, status=400 if "请提供" in err else 404)

            if request.FILES.get("file"):
                tmp_path = template_path

            from apps.documents.services.infrastructure.wiring import get_smart_fill_service
            from apps.documents.services.smart_fill.service import PlaceholderResult

            placeholders = [
                PlaceholderResult(key=p["key"], value=p["value"], source=p.get("source", "llm"))
                for p in placeholders_data
            ]

            service = get_smart_fill_service()
            rendered_bytes = service.render(template_path, placeholders)

            response = HttpResponse(
                rendered_bytes,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            response["Content-Disposition"] = 'attachment; filename="smart_fill_output.docx"'
            return response

        except Exception as e:
            logger.exception("智能填充渲染失败")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def download_view(self, request: Any, pk: int) -> Any:  # pragma: no cover
        """下载文件视图"""
        from django.http import FileResponse, Http404

        from apps.core.exceptions import NotFoundError

        obj = self.get_object(request, str(pk))  # type: ignore[attr-defined]
        if not obj:
            raise Http404("模板不存在")

        try:
            service = _get_admin_service()
            file_path, filename = service.download_file(obj)
        except NotFoundError:
            raise Http404("文件不存在")

        response: Any = FileResponse(Path(file_path).open("rb"), as_attachment=True, filename=filename)
        return response

    def initialize_defaults_view(self, request: Any) -> Any:  # pragma: no cover
        """初始化默认文件模板视图"""
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        from apps.documents.services.document_template.init_service import DocumentTemplateInitService

        try:
            init_service = DocumentTemplateInitService()
            result = init_service.initialize_default_templates()
        except Exception as exc:
            logger.exception("初始化默认模板失败")
            messages.error(request, "初始化失败：%(error)s" % {"error": str(exc)})
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        if not result.get("success", True):
            missing_files = result.get("missing_files", [])
            preview_files = "、".join(str(item) for item in missing_files[:5])
            if len(missing_files) > 5:
                preview_files = f"{preview_files} ..."

            messages.error(
                request,
                "初始化失败：缺少 %(count)s 个模板文件，请先补齐当前模板根目录下对应 docx 文件。当前目录：%(root)s。缺失示例：%(files)s"
                % {"count": len(missing_files), "root": get_docx_templates_root(), "files": preview_files or "-"},
            )
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        msg_parts = []
        if result["folder_created"] > 0:
            msg_parts.append(f"文件夹模板 {result['folder_created']} 个")
        if result["doc_created"] > 0:
            msg_parts.append(f"文件模板 {result['doc_created']} 个")
        if result["binding_created"] > 0:
            msg_parts.append(f"绑定关系 {result['binding_created']} 个")

        if msg_parts:
            messages.success(request, f"✅ 初始化成功！创建了：{' | '.join(msg_parts)}")
        else:
            messages.info(request, "ℹ️ 所有数据已存在，无需初始化")

        return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

    def set_docx_root_view(self, request: Any) -> Any:  # pragma: no cover
        """在线设置私有模板根目录（为空则切回公用目录）。"""
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        if request.method != "POST":
            messages.error(request, "仅支持 POST 请求")
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        raw_value = str(request.POST.get("private_docx_root", "") or "")

        try:
            normalized = _normalize_private_docx_root(raw_value)
            _get_system_config_service().set_value(
                key=PRIVATE_DOCX_ROOT_SETTING,
                value=normalized,
                category="general",
                description="文书模板私有根目录，留空表示使用公用目录",
                is_secret=False,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))
        except Exception as exc:
            logger.exception("更新模板根目录失败")
            messages.error(request, "更新失败：%(error)s" % {"error": str(exc)})
            return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

        if normalized:
            messages.success(request, "模板根目录已更新为：%(path)s" % {"path": normalized})
        else:
            messages.success(request, "已切换为公用模板目录")

        return HttpResponseRedirect(reverse("admin:documents_documenttemplate_changelist"))

    def _get_docx_root_extra_context(self) -> dict[str, str]:  # pragma: no cover
        from django.urls import reverse

        source = get_docx_templates_source()
        source_label = "私有模板目录" if source == "private" else "公用模板目录"
        private_root_input = get_configured_private_docx_templates_root()
        return {
            "docx_templates_source": source,
            "docx_templates_source_label": str(source_label),
            "docx_templates_root": _to_django_relative_path(get_docx_templates_root()),
            "docx_templates_set_root_url": reverse("admin:documents_documenttemplate_set_docx_root"),
            "docx_templates_private_root_input": private_root_input,
        }
