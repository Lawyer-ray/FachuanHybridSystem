"""DocSpace 文档映射服务。

承载 docspace_api 下沉的业务：上传/新建后的本地映射登记（DocSpace 对相同
内容去重，可能已存在映射）、当前律师的文档列表与按 ID 定位（404 语义）、
远端删除与本地记录清理、元数据同步回写。

404/403 语义沿用 ``apps.core.exceptions.NotFoundError``；「未配置默认文件夹」
的入参校验抛 ``ValidationException``（HTTP 400）。响应 Schema 由 API 层组装。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import NotFoundError, ValidationException
from apps.docspace import config
from apps.docspace.models import DocSpaceDocument
from apps.docspace.services.docspace_client import DocSpaceClient

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger(__name__)


class DocSpaceDocumentService:
    """DocSpace 本地映射记录的业务服务。"""

    async def _aget_client(self) -> DocSpaceClient:
        """异步构建 DocSpace 客户端（读取系统配置）。"""
        return DocSpaceClient(portal_url=await config.aget_portal_url(), api_token=await config.aget_api_token())

    async def _upsert_local_mapping(self, *, lawyer: Lawyer, ds_file: Any) -> DocSpaceDocument:
        """登记本地映射记录（DocSpace 对相同内容去重，可能已存在）。"""
        doc, created = await DocSpaceDocument.objects.aget_or_create(
            docspace_file_id=ds_file.id,
            defaults={
                "lawyer": lawyer,
                "title": ds_file.title,
                "docspace_folder_id": ds_file.folder_id,
                "file_ext": ds_file.file_ext,
                "content_length": ds_file.content_length,
                "web_url": ds_file.web_url or "",
            },
        )
        # get_or_create 不更新已存在记录的 web_url，补丁更新
        if not created and not doc.web_url and ds_file.web_url:
            doc.web_url = ds_file.web_url
            await doc.asave(update_fields=["web_url"])
        return doc

    async def upload_file(
        self, *, lawyer: Lawyer, content: bytes, filename: str, folder_id: int | None
    ) -> DocSpaceDocument:
        """上传文件到 DocSpace 并登记本地映射。

        Raises:
            ValidationException: 未配置默认文件夹且未指定 folder_id（HTTP 400）。
        """
        target_folder = folder_id or await config.aget_root_folder_id()
        if not target_folder:
            raise ValidationException("未配置默认文件夹，请指定 folder_id", code="ROOT_FOLDER_NOT_CONFIGURED")

        client = await self._aget_client()
        ds_file = await client.aupload_file(target_folder, filename or "untitled", content)
        return await self._upsert_local_mapping(lawyer=lawyer, ds_file=ds_file)

    async def create_document(self, *, lawyer: Lawyer, title: str) -> DocSpaceDocument:
        """在 DocSpace 新建空白文档并登记本地映射。

        Raises:
            ValidationException: 未配置默认文件夹（HTTP 400）。
        """
        target_folder = await config.aget_root_folder_id()
        if not target_folder:
            raise ValidationException("未配置默认文件夹", code="ROOT_FOLDER_NOT_CONFIGURED")

        client = await self._aget_client()
        ds_file = await client.acreate_empty_docx(target_folder, title)
        return await self._upsert_local_mapping(lawyer=lawyer, ds_file=ds_file)

    async def list_documents(self, *, lawyer: Lawyer, limit: int = 50) -> list[DocSpaceDocument]:
        """列出当前律师的文档（按更新时间倒序，截断 limit 条）。"""
        return [doc async for doc in DocSpaceDocument.objects.filter(lawyer=lawyer).order_by("-updated_at")[:limit]]

    async def get_user_doc(self, *, doc_id: int, lawyer: Lawyer) -> DocSpaceDocument:
        """获取当前律师的文档。

        Raises:
            NotFoundError: 文档不存在或不属于当前律师（HTTP 404）。
        """
        doc = await DocSpaceDocument.objects.filter(id=doc_id, lawyer=lawyer).afirst()
        if doc is None:
            raise NotFoundError("文档不存在")
        return doc

    async def delete_document(self, *, doc_id: int, lawyer: Lawyer) -> None:
        """删除远端文件与本地映射记录（远端不存在时仅告警并继续删本地）。"""
        doc = await self.get_user_doc(doc_id=doc_id, lawyer=lawyer)
        try:
            client = await self._aget_client()
            await client.adelete_file(doc.docspace_file_id)
        except Exception:
            logger.warning("DocSpace 远端删除失败，继续删除本地记录: file_id=%s", doc.docspace_file_id)
        await doc.adelete()

    async def download_document(self, *, doc_id: int, lawyer: Lawyer) -> tuple[bytes, str]:
        """下载文档内容，返回 (内容, 文件名)。"""
        doc = await self.get_user_doc(doc_id=doc_id, lawyer=lawyer)
        client = await self._aget_client()
        return await client.adownload_file(doc.docspace_file_id)

    async def sync_document(self, *, doc_id: int, lawyer: Lawyer) -> DocSpaceDocument:
        """从远端刷新文档元数据并回写本地映射。"""
        doc = await self.get_user_doc(doc_id=doc_id, lawyer=lawyer)
        client = await self._aget_client()
        ds_file = await client.aget_file_info(doc.docspace_file_id)

        # 更新本地映射
        doc.title = ds_file.title
        doc.content_length = ds_file.content_length
        doc.web_url = ds_file.web_url or ""
        doc.last_editor = lawyer
        await doc.asave(update_fields=["title", "content_length", "web_url", "last_editor", "updated_at"])
        return doc
