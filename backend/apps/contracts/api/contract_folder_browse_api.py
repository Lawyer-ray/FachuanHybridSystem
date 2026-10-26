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

from apps.contracts.schemas.folder_browse_schemas import (
    ContractFolderCopyIn,
    ContractFolderEntriesOut,
    ContractFolderEntryNameIn,
    ContractFolderPathIn,
    ContractFolderSaveOut,
)
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


@router.post("/{contract_id}/folder-save", response=ContractFolderSaveOut)
async def save_contract_folder_file(
    request: HttpRequest,
    contract_id: int,
    subpath: str,
    expect_mtime: float | None = None,
) -> Any:
    """原地覆盖保存（编辑器 Ctrl+S）。

    **与 folder-upload 相反**：上传是「不覆盖、同名加序号」；这里是明确的
    覆盖这一份。`expect_mtime` 做乐观锁：与磁盘实际 mtime 不一致就 409，
    避免两人同开时静默丢掉前一个人的修改。

    不保留备份（产品决定）：覆盖即覆盖，版本追溯走审查链路的
    `DocumentVersion`，不靠磁盘上的 `_历史/`。
    """
    data = await _read_single_upload(request)
    return await _call_service(
        "save_file_content",
        request,
        contract_id,
        subpath=subpath,
        data=data,
        expect_mtime=expect_mtime,
    )


@router.post("/{contract_id}/folder-save-as", response=ContractFolderSaveOut)
async def save_contract_folder_file_as(
    request: HttpRequest,
    contract_id: int,
    subpath: str,
    name: str,
) -> Any:
    """另存为新文件（同目录，同名自动加序号，不覆盖）。

    `subpath` 定位源文件（用来找目录），`name` 是新文件名（前端默认给
    `原名[修订版]V1_日期.docx`）。
    """
    data = await _read_single_upload(request)
    return await _call_service("save_new_file", request, contract_id, subpath=subpath, name=name, data=data)


async def _read_single_upload(request: HttpRequest) -> bytes:
    """取 multipart 里的单个文件字节（字段名 `file`）。

    要求 multipart 而不是 JSON：docx 是二进制，base64 塞 JSON 会白白膨胀 33%，
    且大文件会把整个请求体读进内存两次。
    """
    from asgiref.sync import sync_to_async

    from apps.core.exceptions import ValidationException

    files = request.FILES.getlist("file") if hasattr(request, "FILES") else []
    if not files:
        raise ValidationException(message="未收到文件内容", errors={"file": "空"})
    f = files[0]

    def _read() -> bytes:
        f.seek(0)
        # Django 的 UploadedFile.read() 返回 Any：显式收敛成 bytes，
        # 否则 mypy 的 no-any-return 会在 API 层全线报错
        data: bytes = f.read()
        return data

    return await sync_to_async(_read, thread_sensitive=True)()


@router.post("/{contract_id}/folder-rename")
async def rename_contract_folder_entry(request: HttpRequest, contract_id: int, data: ContractFolderEntryNameIn) -> Any:
    """重命名 subpath 指向的文件或文件夹（name 为新名字，同目录内生效）。"""
    return await _call_service("rename", request, contract_id, subpath=data.subpath, new_name=data.name)


@router.post("/{contract_id}/folder-copy")
async def copy_contract_folder_entry(request: HttpRequest, contract_id: int, data: ContractFolderCopyIn) -> Any:
    """复制文件/文件夹到目标目录（同名自动加序号；不覆盖既有文件）。"""
    return await _call_service("copy_entry", request, contract_id, subpath=data.subpath, dest_subpath=data.dest_subpath)


@router.post("/{contract_id}/folder-delete")
async def delete_contract_folder_entry(request: HttpRequest, contract_id: int, data: ContractFolderPathIn) -> Any:
    """删除 = 移入绑定根下 _已删除/（带时间戳，可恢复），不做物理删除。"""
    return await _call_service("delete_entry", request, contract_id, subpath=data.subpath)
