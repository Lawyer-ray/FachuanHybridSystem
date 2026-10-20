"""案件绑定文件夹浏览 + 目录管理 API（前端办案详情页「文件夹视图」数据源）。

端点均为案件 ACL 同口径：浏览（列某一层 / 预览单文件）只读；管理
（新建文件夹 / 拖拽上传 / 重命名）写的是用户本地绑定目录，不进 media 仓库。
挂载进 cases router 后与全局一致走 ``JWTOrSessionAuth``
（Bearer 头 / ``?ticket=`` 短时票据 / Session）——前端用
``POST /api/v1/download-ticket`` 换票后 ``window.open`` 即可预览。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.http import FileResponse, HttpRequest
from ninja import Router

from apps.cases.schemas import CaseFolderEntriesResponseSchema, CaseFolderEntryNameIn
from apps.core.http.download import content_disposition
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.cases.api")
router = Router()

# 与 media 保护视图同源的安全口径：html/svg/js 等经直链 inline 返回会在同源执行脚本
_DANGEROUS_EXTENSIONS = frozenset({".html", ".htm", ".svg", ".xhtml", ".xml", ".js", ".mjs", ".xsl", ".xslt"})


def _get_folder_browse_service() -> Any:
    from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService

    return CaseFolderBrowseService()


async def _call_service(method: str, request: HttpRequest, case_id: int, **kwargs: Any) -> Any:
    """统一：ACL 上下文提取 + sync service 调用（案件 ACL 在 service 内）。"""
    service = _get_folder_browse_service()
    ctx = get_request_access_context(request)
    fn = getattr(service, method)
    return await sync_to_async(fn)(
        owner_id=case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        **kwargs,
    )


@router.get("/{case_id}/folder-entries", response=CaseFolderEntriesResponseSchema)
async def list_case_folder_entries(request: HttpRequest, case_id: int, subpath: str = "") -> Any:
    """列出案件绑定文件夹下某一层的子文件夹与文件（非递归，不含隐藏项）。"""
    return await _call_service("list_entries", request, case_id, subpath=subpath)


@router.get("/{case_id}/folder-file")
async def open_case_folder_file(request: HttpRequest, case_id: int, subpath: str) -> FileResponse:
    """内联预览（或下载）绑定文件夹内的单个文件。"""
    abs_path: Path = await _call_service("resolve_file", request, case_id, subpath=subpath)

    content_type = mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream"
    force_download = abs_path.suffix.lower() in _DANGEROUS_EXTENSIONS or content_type.startswith("text/html")
    if force_download:
        content_type = "application/octet-stream"

    logger.info(
        "case_folder_file_open",
        extra={"action": "case_folder_file_open", "case_id": case_id, "file_name": abs_path.name},
    )
    response = FileResponse(open(abs_path, "rb"), content_type=content_type)
    response["Content-Disposition"] = content_disposition(abs_path.name, inline=not force_download)
    return response


@router.post("/{case_id}/folder-mkdir")
async def create_case_folder(request: HttpRequest, case_id: int, data: CaseFolderEntryNameIn) -> Any:
    """在 subpath（空 = 绑定根）下新建子文件夹。"""
    return await _call_service("mkdir", request, case_id, subpath=data.subpath, name=data.name)


@router.post("/{case_id}/folder-upload")
async def upload_case_folder_files(request: HttpRequest, case_id: int, subpath: str = "") -> Any:
    """拖拽 / 多文件上传到 subpath 目录（multipart 字段名 files，同名自动加序号）。"""
    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []
    return await _call_service("save_uploads", request, case_id, subpath=subpath, files=files)


@router.post("/{case_id}/folder-rename")
async def rename_case_folder_entry(request: HttpRequest, case_id: int, data: CaseFolderEntryNameIn) -> Any:
    """重命名 subpath 指向的文件或文件夹（new_name 同目录内生效）。"""
    return await _call_service("rename", request, case_id, subpath=data.subpath, new_name=data.name)
