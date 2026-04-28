"""Admin 导入导出公共 Mixin（ZIP 格式，含文件）。"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger("apps.core")


class AdminImportExportMixin:
    """
    为 ModelAdmin 提供 ZIP 格式导入导出功能。

    ZIP 结构：
        data.json          ← 纯数据，file_path 字段保持相对路径
        files/             ← 媒体文件（按需，可无）
            client_docs/zhangsan_id_card.pdf
            ...

    子类需实现：
    - export_model_name: str
    - handle_json_import(data: list[dict], user: str, zip_file: zipfile.ZipFile | None)
      → tuple[int, int, list[str]]  (成功, 跳过, 错误列表)
    - serialize_queryset(queryset) → list[dict]
    - get_file_paths(queryset) → list[str]  （返回需要打包的相对路径列表，默认空）
    """

    export_model_name: str = "export"

    def get_file_paths(self, queryset: QuerySet[Any]) -> list[str]:
        """子类覆盖此方法返回需要打包进 ZIP 的文件相对路径列表。"""
        return []

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()  # type: ignore[misc]
        custom = [
            path("import/", self.admin_site.admin_view(self.import_view), name=f"{self.export_model_name}_import"),  # type: ignore[attr-defined]
        ]
        return custom + urls

    def import_view(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return redirect(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"  # type: ignore[attr-defined]
            )
        if not self.has_add_permission(request):  # type: ignore[attr-defined]
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        uploaded = request.FILES.get("json_file")
        if not uploaded:
            messages.error(request, _("请选择文件"))
        else:
            try:
                success, skipped, errors = self._process_import(uploaded, str(request.user))
                messages.success(
                    request,
                    _("导入完成：成功 %(s)d 条，跳过 %(k)d 条") % {"s": success, "k": skipped},
                )
                for err in errors:
                    messages.warning(request, err)
            except Exception as exc:
                logger.exception("导入失败")
                messages.error(request, _("导入失败: %(err)s") % {"err": str(exc)})

        return redirect(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"  # type: ignore[attr-defined]
        )

    def _process_import(self, uploaded: Any, user: str) -> tuple[int, int, list[str]]:
        raw_bytes: bytes = uploaded.read()

        if not zipfile.is_zipfile(io.BytesIO(raw_bytes)):
            raise ValueError(_("请上传 ZIP 文件"))

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            if "data.json" not in zf.namelist():
                raise ValueError(_("ZIP 中缺少 data.json"))
            envelope = json.loads(zf.read("data.json").decode("utf-8"))
            # 校验 _type 标记
            if not isinstance(envelope, dict) or envelope.get("_type") != self.export_model_name:
                raise ValueError(
                    _("文件类型不匹配：期望 %(expected)s，实际 %(actual)s")
                    % {
                        "expected": self.export_model_name,
                        "actual": envelope.get("_type") if isinstance(envelope, dict) else type(envelope).__name__,
                    }
                )
            data_list = envelope.get("data", [])
            if not isinstance(data_list, list):
                raise ValueError(_("data.json 格式错误：data 字段必须为数组"))
            # 校验每条记录必填字段
            required = getattr(self, "import_required_fields", ())
            for i, item in enumerate(data_list, 1):
                if not isinstance(item, dict):
                    raise ValueError(_("第 %(i)d 条记录格式错误") % {"i": i})
                missing = [f for f in required if not item.get(f)]
                if missing:
                    raise ValueError(
                        _("第 %(i)d 条记录缺少必填字段: %(fields)s") % {"i": i, "fields": ", ".join(missing)}
                    )
            self._extract_files(zf)
            return self.handle_json_import(data_list, user, zf)  # type: ignore[attr-defined,no-any-return]

    def _extract_files(self, zf: zipfile.ZipFile) -> None:
        """把 ZIP 内 files/ 目录下的文件写入 MEDIA_ROOT。"""
        from apps.core.services.storage_service import _get_media_root

        media_root = _get_media_root()
        if not media_root:
            return
        root = Path(media_root).resolve()
        for name in zf.namelist():
            if not name.startswith("files/") or name.endswith("/"):
                continue
            rel = name[len("files/") :]  # 去掉 files/ 前缀
            dest = (root / rel).resolve()
            # 防止 Zip Slip 路径遍历攻击（relative_to 抛异常即拒绝）
            try:
                dest.relative_to(root)
            except ValueError:
                logger.warning("跳过可疑路径", extra={"path": name})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():  # 已存在则不覆盖
                dest.write_bytes(zf.read(name))
                logger.info("还原文件", extra={"path": str(dest)})

    # ── 导出 actions ──────────────────────────────────────────────

    def export_selected_as_json(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponse:
        count = queryset.count()
        filename = f"{self.export_model_name}_selected_{count}_export_{date.today().strftime('%Y%m%d')}.zip"
        return self._build_zip_response(queryset, filename)

    export_selected_as_json.short_description = _("导出选中")  # type: ignore[attr-defined]

    def export_all_as_json(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponse:
        all_qs = self.get_queryset(request)  # type: ignore[attr-defined]
        filename = f"{self.export_model_name}_all_export_{date.today().strftime('%Y%m%d')}.zip"
        return self._build_zip_response(all_qs, filename)

    export_all_as_json.short_description = _("导出全部")  # type: ignore[attr-defined]

    def _build_zip_response(self, queryset: QuerySet[Any], filename: str) -> HttpResponse:
        from apps.core.services.storage_service import _get_media_root

        data = self.serialize_queryset(queryset)  # type: ignore[attr-defined]
        file_paths = self.get_file_paths(queryset)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            envelope = {"_type": self.export_model_name, "data": data}
            zf.writestr("data.json", json.dumps(envelope, ensure_ascii=False, indent=2, default=str))

            if file_paths:
                media_root = _get_media_root()
                root = Path(media_root) if media_root else None
                for rel_path in file_paths:
                    if not rel_path:
                        continue
                    abs_path = (root / rel_path) if root else Path(rel_path)
                    if abs_path.exists():
                        zf.write(abs_path, f"files/{rel_path}")
                    else:
                        logger.warning("导出时文件不存在，跳过", extra={"path": str(abs_path)})

        buf.seek(0)
        response = HttpResponse(buf.read(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
