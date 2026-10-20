"""案件绑定文件夹浏览 API（前端办案详情页「文件夹视图」数据源）。

两个端点均为只读：``folder-entries`` 列某一层子项，``folder-file`` 内联
预览单文件。挂载进 cases router 后与全局一致走 ``JWTOrSessionAuth``
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

from apps.cases.schemas import CaseFolderEntriesResponseSchema
from apps.core.http.download import content_disposition
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.cases.api")
router = Router()

# 与 media 保护视图同源的安全口径：html/svg/js 等经直链 inline 返回会在同源执行脚本
_DANGEROUS_EXTENSIONS = frozenset({".html", ".htm", ".svg", ".xhtml", ".xml", ".js", ".mjs", ".xsl", ".xslt"})


def _get_folder_browse_service() -> Any:
    from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService

    return CaseFolderBrowseService()


@router.get("/{case_id}/folder-entries", response=CaseFolderEntriesResponseSchema)
async def list_case_folder_entries(request: HttpRequest, case_id: int, subpath: str = "") -> Any:
    """列出案件绑定文件夹下某一层的子文件夹与文件（非递归，不含隐藏项）。"""
    service = _get_folder_browse_service()
    ctx = get_request_access_context(request)

    result = await sync_to_async(service.list_entries)(
        case_id=case_id,
        subpath=subpath,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return CaseFolderEntriesResponseSchema(**result)


@router.get("/{case_id}/folder-file")
async def open_case_folder_file(request: HttpRequest, case_id: int, subpath: str) -> FileResponse:
    """内联预览（或下载）绑定文件夹内的单个文件。"""
    service = _get_folder_browse_service()
    ctx = get_request_access_context(request)

    abs_path: Path = await sync_to_async(service.resolve_file)(
        case_id=case_id,
        subpath=subpath,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )

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
