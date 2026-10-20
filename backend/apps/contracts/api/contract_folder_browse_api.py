"""合同绑定文件夹浏览 + 目录管理 API（前端详情页右栏「合同文件夹」树数据源）。

与案件级 ``apps/cases/api/case_folder_browse_api.py`` 同构：浏览只读、管理
（新建 / 上传 / 重命名）写用户本地绑定目录；合同行级 ACL 在 service 内。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.http import FileResponse, HttpRequest
from ninja import Router

from apps.contracts.schemas.folder_browse_schemas import ContractFolderEntriesOut, ContractFolderEntryNameIn
from apps.core.http.download import content_disposition
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.contracts.api")
router = Router()

_DANGEROUS_EXTENSIONS = frozenset({".html", ".htm", ".svg", ".xhtml", ".xml", ".js", ".mjs", ".xsl", ".xslt"})


def _get_folder_browse_service() -> Any:
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    return ContractFolderBrowseService()


async def _call_service(method: str, request: HttpRequest, contract_id: int, **kwargs: Any) -> Any:
    service = _get_folder_browse_service()
    ctx = get_request_access_context(request)
    fn = getattr(service, method)
    return await sync_to_async(fn)(
        owner_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        **kwargs,
    )


@router.get("/{contract_id}/folder-entries", response=ContractFolderEntriesOut)
async def list_contract_folder_entries(request: HttpRequest, contract_id: int, subpath: str = "") -> Any:
    """列出合同绑定文件夹下某一层的子文件夹与文件（非递归，不含隐藏项）。"""
    return await _call_service("list_entries", request, contract_id, subpath=subpath)


@router.get("/{contract_id}/folder-file")
async def open_contract_folder_file(request: HttpRequest, contract_id: int, subpath: str) -> FileResponse:
    """内联预览（或下载）绑定文件夹内的单个文件。"""
    abs_path: Path = await _call_service("resolve_file", request, contract_id, subpath=subpath)

    content_type = mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream"
    force_download = abs_path.suffix.lower() in _DANGEROUS_EXTENSIONS or content_type.startswith("text/html")
    if force_download:
        content_type = "application/octet-stream"

    logger.info(
        "contract_folder_file_open",
        extra={"action": "contract_folder_file_open", "contract_id": contract_id, "file_name": abs_path.name},
    )
    response = FileResponse(open(abs_path, "rb"), content_type=content_type)
    response["Content-Disposition"] = content_disposition(abs_path.name, inline=not force_download)
    return response


@router.post("/{contract_id}/folder-mkdir")
async def create_contract_folder(request: HttpRequest, contract_id: int, data: ContractFolderEntryNameIn) -> Any:
    """在 subpath（空 = 绑定根）下新建子文件夹。"""
    return await _call_service("mkdir", request, contract_id, subpath=data.subpath, name=data.name)


@router.post("/{contract_id}/folder-upload")
async def upload_contract_folder_files(request: HttpRequest, contract_id: int, subpath: str = "") -> Any:
    """拖拽 / 多文件上传到 subpath 目录（multipart 字段名 files，同名自动加序号）。"""
    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []
    return await _call_service("save_uploads", request, contract_id, subpath=subpath, files=files)


@router.post("/{contract_id}/folder-rename")
async def rename_contract_folder_entry(request: HttpRequest, contract_id: int, data: ContractFolderEntryNameIn) -> Any:
    """重命名 subpath 指向的文件或文件夹（name 为新名字，同目录内生效）。"""
    return await _call_service("rename", request, contract_id, subpath=data.subpath, new_name=data.name)
