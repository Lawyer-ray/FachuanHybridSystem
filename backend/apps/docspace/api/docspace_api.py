"""DocSpace API — 文档管理接口。"""

from __future__ import annotations

import logging

from django.http import FileResponse, HttpRequest
from ninja import File, Form, Router, UploadedFile

from apps.docspace import config
from apps.docspace.models import DocSpaceDocument
from apps.docspace.schemas import DocSpaceConfigOut, DocSpaceDocumentOut, DocSpaceUploadOut
from apps.docspace.services.docspace_client import DocSpaceClient

router = Router()

logger = logging.getLogger(__name__)


def _get_client() -> DocSpaceClient:
    """获取 DocSpace 客户端实例。"""
    return DocSpaceClient(portal_url=config.get_portal_url(), api_token=config.get_api_token())


# ── 配置 ──────────────────────────────────────────────────


@router.get("/config", response=DocSpaceConfigOut, summary="获取 DocSpace 配置")
def get_docspace_config(request: HttpRequest) -> DocSpaceConfigOut:
    return DocSpaceConfigOut(
        portal_url=config.get_portal_url(),
        enabled=config.is_configured(),
    )


# ── 上传 ──────────────────────────────────────────────────


@router.post("/upload", response=DocSpaceUploadOut, summary="上传文件到 DocSpace")
def upload_file(
    request: HttpRequest,
    file: UploadedFile = File(...),
    folder_id: int | None = Form(default=None),
) -> DocSpaceUploadOut:
    target_folder = folder_id or config.get_root_folder_id()
    if not target_folder:
        from ninja.errors import HttpError

        raise HttpError(400, "未配置默认文件夹，请指定 folder_id")

    content = file.read()
    client = _get_client()
    ds_file = client.upload_file(target_folder, file.name or "untitled", content)

    # 创建本地映射记录（DocSpace 对相同内容去重，可能已存在）
    doc, _ = DocSpaceDocument.objects.get_or_create(
        docspace_file_id=ds_file.id,
        defaults={
            "lawyer": request.auth,  # type: ignore[arg-type]
            "title": ds_file.title,
            "docspace_folder_id": ds_file.folder_id,
            "file_ext": ds_file.file_ext,
            "content_length": ds_file.content_length,
        },
    )

    return DocSpaceUploadOut(
        id=doc.id,
        title=doc.title,
        docspace_file_id=doc.docspace_file_id,
        web_url=ds_file.web_url,
        file_ext=doc.file_ext,
        content_length=doc.content_length,
    )


# ── 新建 ──────────────────────────────────────────────────


@router.post("/create", response=DocSpaceUploadOut, summary="新建空白文档")
def create_document(
    request: HttpRequest,
    title: str = Form(default="新建文档.docx"),
) -> DocSpaceUploadOut:
    target_folder = config.get_root_folder_id()
    if not target_folder:
        from ninja.errors import HttpError

        raise HttpError(400, "未配置默认文件夹")

    client = _get_client()
    ds_file = client.create_empty_docx(target_folder, title)

    # DocSpace 对相同内容去重，可能已存在
    doc, _ = DocSpaceDocument.objects.get_or_create(
        docspace_file_id=ds_file.id,
        defaults={
            "lawyer": request.auth,  # type: ignore[arg-type]
            "title": ds_file.title,
            "docspace_folder_id": ds_file.folder_id,
            "file_ext": ds_file.file_ext,
            "content_length": ds_file.content_length,
        },
    )

    return DocSpaceUploadOut(
        id=doc.id,
        title=doc.title,
        docspace_file_id=doc.docspace_file_id,
        web_url=ds_file.web_url,
        file_ext=doc.file_ext,
        content_length=doc.content_length,
    )


# ── 文档列表 ──────────────────────────────────────────────


@router.get("/documents", response=list[DocSpaceDocumentOut], summary="列出当前用户的文档")
def list_documents(request: HttpRequest) -> list[DocSpaceDocumentOut]:
    docs = DocSpaceDocument.objects.filter(lawyer=request.auth).order_by("-updated_at")[:50]  # type: ignore[attr-defined]
    results: list[DocSpaceDocumentOut] = []
    for doc in docs:
        out = DocSpaceDocumentOut.model_validate(doc)
        # 尝试从缓存/DB 填充 web_url（首次查询时从 DocSpace 获取）
        if not out.web_url:
            try:
                client = _get_client()
                ds_file = client.get_file_info(doc.docspace_file_id)
                out.web_url = ds_file.web_url
            except Exception:
                logger.debug("无法获取 DocSpace 文件信息: file_id=%s", doc.docspace_file_id)
        results.append(out)
    return results


# ── 文档详情 ──────────────────────────────────────────────


@router.get("/documents/{doc_id}", response=DocSpaceDocumentOut, summary="获取文档详情")
def get_document(request: HttpRequest, doc_id: int) -> DocSpaceDocumentOut:
    doc = _get_user_doc(request, doc_id)
    out = DocSpaceDocumentOut.model_validate(doc)
    if not out.web_url:
        try:
            client = _get_client()
            ds_file = client.get_file_info(doc.docspace_file_id)
            out.web_url = ds_file.web_url
        except Exception:
            logger.debug("无法获取 DocSpace 文件信息: file_id=%s", doc.docspace_file_id)
    return out


# ── 删除 ──────────────────────────────────────────────────


@router.delete("/documents/{doc_id}", summary="删除文档")
def delete_document(request: HttpRequest, doc_id: int) -> dict[str, bool]:
    doc = _get_user_doc(request, doc_id)
    # 删除远端文件（忽略远端不存在的情况）
    try:
        client = _get_client()
        client.delete_file(doc.docspace_file_id)
    except Exception:
        logger.warning("DocSpace 远端删除失败，继续删除本地记录: file_id=%s", doc.docspace_file_id)
    doc.delete()
    return {"ok": True}


# ── 下载 ──────────────────────────────────────────────────


@router.get("/documents/{doc_id}/download", summary="下载文档")
def download_document(request: HttpRequest, doc_id: int) -> FileResponse:
    doc = _get_user_doc(request, doc_id)
    client = _get_client()
    content, filename = client.download_file(doc.docspace_file_id)

    import io

    return FileResponse(
        io.BytesIO(content),
        as_attachment=True,
        filename=filename,
    )


# ── 同步 ──────────────────────────────────────────────────


@router.post("/sync/{doc_id}", response=DocSpaceDocumentOut, summary="刷新文档元数据")
def sync_document(request: HttpRequest, doc_id: int) -> DocSpaceDocumentOut:
    doc = _get_user_doc(request, doc_id)
    client = _get_client()
    ds_file = client.get_file_info(doc.docspace_file_id)

    # 更新本地映射
    doc.title = ds_file.title
    doc.content_length = ds_file.content_length
    doc.last_editor = request.auth  # type: ignore[attr-defined]
    doc.save(update_fields=["title", "content_length", "last_editor", "updated_at"])

    out = DocSpaceDocumentOut.model_validate(doc)
    out.web_url = ds_file.web_url
    return out


# ── 工具函数 ──────────────────────────────────────────────


def _get_user_doc(request: HttpRequest, doc_id: int) -> DocSpaceDocument:
    """获取当前用户的文档，不存在则 404。"""
    from ninja.errors import HttpError

    doc = DocSpaceDocument.objects.filter(id=doc_id, lawyer=request.auth).first()  # type: ignore[attr-defined]
    if doc is None:
        raise HttpError(404, "文档不存在")
    return doc
