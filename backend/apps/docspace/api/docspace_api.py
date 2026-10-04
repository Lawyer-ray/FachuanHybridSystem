"""DocSpace API — 文档管理接口。"""

from __future__ import annotations

import io
from pathlib import Path

from django.http import FileResponse, HttpRequest
from ninja import File, Form, Router, UploadedFile

from apps.core.exceptions import ValidationException
from apps.core.security.auth import JWTOrSessionAuth
from apps.docspace.schemas import DocSpaceConfigOut, DocSpaceDocumentOut, DocSpaceUploadOut
from apps.docspace.services.document_service import DocSpaceDocumentService

router = Router(auth=JWTOrSessionAuth())

# 上传白名单：DocSpace 为文档空间，仅接受常见办公文档格式
_DOCSPACE_ALLOWED_EXTENSIONS = frozenset(
    {".docx", ".doc", ".pdf", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md", ".csv"}
)
# 单文件上限 50MB（与仓库内其他上传口的先例一致）
_DOCSPACE_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


def _validate_upload(file: UploadedFile) -> None:
    """校验上传文件的扩展名与大小，拒绝后才 read()，避免大文件全量进内存。"""
    ext = Path(str(file.name or "")).suffix.lower()
    if ext not in _DOCSPACE_ALLOWED_EXTENSIONS:
        raise ValidationException(
            f"不支持的文件格式: {ext or '(无扩展名)'}",
            code="INVALID_FILE_TYPE",
            errors={"file": f"允许的格式: {', '.join(sorted(_DOCSPACE_ALLOWED_EXTENSIONS))}"},
        )
    if int(getattr(file, "size", 0) or 0) > _DOCSPACE_MAX_UPLOAD_SIZE_BYTES:
        raise ValidationException("文件过大", code="FILE_TOO_LARGE", errors={"file": "文件不能超过 50MB"})


def _get_document_service() -> DocSpaceDocumentService:
    """工厂函数：创建 DocSpace 文档服务实例。"""
    return DocSpaceDocumentService()


# ── 配置 ──────────────────────────────────────────────────


@router.get("/config", response=DocSpaceConfigOut, summary="获取 DocSpace 配置")
def get_docspace_config(request: HttpRequest) -> DocSpaceConfigOut:
    from apps.docspace import config

    return DocSpaceConfigOut(
        portal_url=config.get_portal_url(),
        enabled=config.is_configured(),
    )


# ── 上传 ──────────────────────────────────────────────────


@router.post("/upload", response=DocSpaceUploadOut, summary="上传文件到 DocSpace")
async def upload_file(
    request: HttpRequest,
    file: UploadedFile = File(...),
    folder_id: int | None = Form(default=None),
) -> DocSpaceUploadOut:
    _validate_upload(file)
    service = _get_document_service()
    doc = await service.upload_file(
        lawyer=request.auth,  # type: ignore[attr-defined]
        content=file.read(),
        filename=file.name or "untitled",
        folder_id=folder_id,
    )
    return DocSpaceUploadOut(
        id=doc.id,
        title=doc.title,
        docspace_file_id=doc.docspace_file_id,
        web_url=doc.web_url,
        file_ext=doc.file_ext,
        content_length=doc.content_length,
    )


# ── 新建 ──────────────────────────────────────────────────


@router.post("/create", response=DocSpaceUploadOut, summary="新建空白文档")
async def create_document(
    request: HttpRequest,
    title: str = Form(default="新建文档.docx"),
) -> DocSpaceUploadOut:
    service = _get_document_service()
    doc = await service.create_document(lawyer=request.auth, title=title)  # type: ignore[attr-defined]
    return DocSpaceUploadOut(
        id=doc.id,
        title=doc.title,
        docspace_file_id=doc.docspace_file_id,
        web_url=doc.web_url,
        file_ext=doc.file_ext,
        content_length=doc.content_length,
    )


# ── 文档列表 ──────────────────────────────────────────────


@router.get("/documents", response=list[DocSpaceDocumentOut], summary="列出当前用户的文档")
async def list_documents(request: HttpRequest) -> list[DocSpaceDocumentOut]:
    service = _get_document_service()
    docs = await service.list_documents(lawyer=request.auth)  # type: ignore[attr-defined]
    return [DocSpaceDocumentOut.model_validate(doc) for doc in docs]


# ── 文档详情 ──────────────────────────────────────────────


@router.get("/documents/{doc_id}", response=DocSpaceDocumentOut, summary="获取文档详情")
async def get_document(request: HttpRequest, doc_id: int) -> DocSpaceDocumentOut:
    service = _get_document_service()
    doc = await service.get_user_doc(doc_id=doc_id, lawyer=request.auth)  # type: ignore[attr-defined]
    return DocSpaceDocumentOut.model_validate(doc)


# ── 删除 ──────────────────────────────────────────────────


@router.delete("/documents/{doc_id}", summary="删除文档")
async def delete_document(request: HttpRequest, doc_id: int) -> dict[str, bool]:
    service = _get_document_service()
    await service.delete_document(doc_id=doc_id, lawyer=request.auth)  # type: ignore[attr-defined]
    return {"ok": True}


# ── 下载 ──────────────────────────────────────────────────


@router.get("/documents/{doc_id}/download", summary="下载文档")
async def download_document(request: HttpRequest, doc_id: int) -> FileResponse:
    service = _get_document_service()
    content, filename = await service.download_document(doc_id=doc_id, lawyer=request.auth)  # type: ignore[attr-defined]
    return FileResponse(
        io.BytesIO(content),
        as_attachment=True,
        filename=filename,
    )


# ── 同步 ──────────────────────────────────────────────────


@router.post("/sync/{doc_id}", response=DocSpaceDocumentOut, summary="刷新文档元数据")
async def sync_document(request: HttpRequest, doc_id: int) -> DocSpaceDocumentOut:
    service = _get_document_service()
    doc = await service.sync_document(doc_id=doc_id, lawyer=request.auth)  # type: ignore[attr-defined]
    return DocSpaceDocumentOut.model_validate(doc)
