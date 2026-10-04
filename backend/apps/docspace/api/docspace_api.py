"""DocSpace API — 文档管理接口。"""

from __future__ import annotations

import io

from django.http import FileResponse, HttpRequest
from ninja import File, Form, Router, UploadedFile

from apps.core.security.auth import JWTOrSessionAuth
from apps.docspace.schemas import DocSpaceConfigOut, DocSpaceDocumentOut, DocSpaceUploadOut
from apps.docspace.services.document_service import DocSpaceDocumentService

router = Router(auth=JWTOrSessionAuth())


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
