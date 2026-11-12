"""案件 Admin 的本地文件夹打开与邮件文件夹批量导入视图。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest, HttpResponse

from apps.cases.models import Case

logger = logging.getLogger("apps.cases")


class CaseAdminFolderImportMixin:  # pragma: no cover
    """打开案件绑定文件夹、从文件夹批量导入案件日志。"""

    if TYPE_CHECKING:
        # 以下成员本 mixin 不拥有，只是声明签名供自身类型标注：
        # _ensure_case_access 的唯一实现在 CaseAdminDetailViewsMixin，
        # has_view_permission 来自 ModelAdmin。
        def _ensure_case_access(
            self, request: HttpRequest, case: Case | None, *, case_id: int | None = None
        ) -> None:  # pragma: no cover
            raise NotImplementedError  # 仅为类型检查声明，运行时由 CaseAdminDetailViewsMixin 提供

        def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
            raise NotImplementedError  # 同上

    def open_folder_view(self, request: HttpRequest, object_id: int) -> HttpResponse:  # pragma: no cover
        """打开案件绑定的本地文件夹（Finder/资源管理器）"""
        import platform
        import subprocess
        from pathlib import Path

        from django.http import JsonResponse

        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        if not self.has_view_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": "无权限"}, status=403)

        self._ensure_case_access(request, None, case_id=object_id)

        try:
            from apps.cases.models.material import CaseFolderBinding

            try:
                binding = CaseFolderBinding.objects.get(case_id=object_id)
            except CaseFolderBinding.DoesNotExist:
                return JsonResponse({"success": False, "error": "未绑定文件夹"}, status=404)

            folder_path = binding.resolved_folder_path
            if not folder_path:
                return JsonResponse({"success": False, "error": "文件夹路径为空"}, status=400)

            folder = Path(folder_path).expanduser().resolve()
            if not folder.exists():
                return JsonResponse(
                    {"success": False, "error": str("文件夹不存在: %(path)s" % {"path": folder_path})}, status=404
                )

            # 安全检查：只允许打开用户主目录、MEDIA_ROOT 或 /Volumes 下的目录（防止打开系统敏感目录）
            from django.conf import settings

            home = Path.home().resolve()
            volumes = Path("/Volumes").resolve()
            media_root = Path(settings.MEDIA_ROOT).resolve()
            if not (folder.is_relative_to(home) or folder.is_relative_to(volumes) or folder.is_relative_to(media_root)):
                return JsonResponse({"success": False, "error": "不允许打开该目录"}, status=403)

            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", str(folder)])  # noqa: S607
            elif system == "Windows":
                subprocess.Popen(["explorer", str(folder)])  # noqa: S607
            else:
                subprocess.Popen(["xdg-open", str(folder)])  # noqa: S607

            logger.info("已打开案件文件夹: %s, case_id=%s", folder_path, object_id)
            return JsonResponse({"success": True, "folder_path": folder_path})
        except Exception:
            logger.exception("打开案件文件夹失败: case_id=%s", object_id)
            return JsonResponse({"success": False, "error": "打开文件夹失败，请查看服务器日志"}, status=500)

    def email_folder_import_view(self, request: HttpRequest, object_id: int) -> HttpResponse:  # pragma: no cover
        """从案件绑定文件夹的第一层级子目录批量导入案件日志"""
        import json as json_mod

        from django.http import JsonResponse

        if not self.has_view_permission(request):  # type: ignore[attr-defined]
            return JsonResponse({"success": False, "error": "无权限"}, status=403)

        self._ensure_case_access(request, None, case_id=object_id)

        try:
            from apps.cases.models.material import CaseFolderBinding

            binding = CaseFolderBinding.objects.filter(case_id=object_id).first()
            if not binding or not binding.resolved_folder_path:
                return JsonResponse({"success": False, "error": "未绑定文件夹"}, status=404)

            if request.method == "GET":
                # 列出第一层级所有子文件夹，让用户自己选
                storage_type = getattr(binding, "storage_type", "local")

                if storage_type != "local" and getattr(binding, "storage_account", None) is not None:
                    from apps.cloud_storage.factory import create_provider_for_binding

                    provider = create_provider_for_binding(binding)
                    try:
                        children = provider.list_directory(binding.resolved_folder_path)
                    except Exception:
                        logger.exception(
                            "云存储列目录失败: case_id=%s, path=%s", object_id, binding.resolved_folder_path
                        )
                        return JsonResponse({"success": False, "error": "云存储访问失败"}, status=500)

                    subfolders = []
                    for child in children:
                        if not child.is_dir or child.name.startswith("."):
                            continue
                        subfolders.append(
                            {
                                "relative_path": child.name,
                                "display_name": child.name,
                            }
                        )
                    subfolders.sort(key=lambda x: x["display_name"].lower())
                    return JsonResponse({"success": True, "subfolders": subfolders})

                from pathlib import Path

                root = Path(binding.resolved_folder_path).expanduser().resolve()
                if not root.exists():
                    return JsonResponse({"success": False, "error": "文件夹不存在"}, status=404)

                subfolders = []
                for local_child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                    if not local_child.is_dir() or local_child.name.startswith("."):
                        continue
                    subfolders.append(
                        {
                            "relative_path": local_child.name,
                            "display_name": local_child.name,
                        }
                    )

                return JsonResponse({"success": True, "subfolders": subfolders})

            if request.method == "POST":
                # 执行导入
                body = json_mod.loads(request.body) if request.body else {}
                subfolder = body.get("subfolder", "")
                if not subfolder:
                    return JsonResponse({"success": False, "error": "请指定子文件夹"}, status=400)

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
                msg = "导入完成：新增 %(count)s 条日志，跳过 %(skipped)s 条（已存在）" % {
                    "count": log_count,
                    "skipped": skipped,
                }
                logger.info("案件 %s 邮件导入完成: 新增=%s, 跳过=%s", object_id, log_count, skipped)
                return JsonResponse(
                    {"success": True, "message": msg, "imported_count": log_count, "skipped_count": skipped}
                )

            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        except Exception:
            logger.exception("邮件文件夹导入失败: case_id=%s", object_id)
            return JsonResponse({"success": False, "error": "导入失败，请查看服务器日志"}, status=500)


__all__: list[str] = ["CaseAdminFolderImportMixin"]
