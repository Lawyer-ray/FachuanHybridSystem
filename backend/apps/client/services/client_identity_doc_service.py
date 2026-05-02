"""当事人证件文档服务。"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.client.models import Client, ClientIdentityDoc
from apps.client.ports import FileUploadPort
from apps.core.services.storage_service import (
    _get_media_root,
    delete_media_file,
    sanitize_upload_filename,
    save_uploaded_file,
)
from apps.client.services.wiring import get_file_upload_port
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.client")


class ClientIdentityDocService:
    """当事人证件服务"""

    def __init__(self, file_upload_port: FileUploadPort | None = None) -> None:
        """初始化服务。

        Args:
            file_upload_port: 可选的文件上传端口，用于依赖注入
        """
        self._file_upload_port = file_upload_port

    @property
    def file_upload_port(self) -> FileUploadPort:
        """获取文件上传端口（延迟初始化）。"""
        if self._file_upload_port is None:
            self._file_upload_port = get_file_upload_port()
        return self._file_upload_port

    @transaction.atomic
    def add_identity_doc(self, client_id: int, doc_type: str, file_path: str, user: Any = None) -> ClientIdentityDoc:
        """添加当事人证件"""

        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": _("ID 为 %(id)s 的当事人不存在") % {"id": client_id}},
            )

        # 创建证件记录
        doc = ClientIdentityDoc.objects.create(client=client, doc_type=doc_type, file_path=file_path)

        # 重命名文件（对所有非空路径执行），在事务提交后执行文件系统操作
        if file_path:
            transaction.on_commit(lambda doc_id=doc.pk: self._rename_uploaded_file_by_id(doc_id))  # type: ignore[misc]

        return doc

    def _rename_uploaded_file_by_id(self, doc_id: int) -> None:
        """事务提交后重命名文件（避免文件系统操作在事务内执行）。"""
        try:
            doc = self.get_identity_doc(doc_id)
            self.rename_uploaded_file(doc)
        except Exception:
            logger.exception("文件重命名失败", extra={"doc_id": doc_id})

    def rename_uploaded_file(self, doc_instance: ClientIdentityDoc) -> None:
        """重命名上传的文件"""
        if not doc_instance.file_path or not doc_instance.client:
            return

        raw_path = doc_instance.file_path
        media_root_str = _get_media_root()
        # 相对路径通过 MEDIA_ROOT 解析为绝对路径
        p = Path(raw_path)
        if not p.is_absolute():
            abs_path = Path(media_root_str) / p if media_root_str else p
        else:
            abs_path = p

        if not abs_path.exists():
            return

        ext = abs_path.suffix
        client_name = sanitize_upload_filename(doc_instance.client.name)
        doc_type_display = sanitize_upload_filename(str(doc_instance.get_doc_type_display()))
        new_filename = f"{doc_type_display}_{client_name}{ext}"

        old_dir = abs_path.parent
        new_abs_path = old_dir / new_filename

        if new_abs_path.exists() and abs_path.resolve() != new_abs_path.resolve():
            counter = 1
            name_without_ext = f"{doc_type_display}_{client_name}"
            while new_abs_path.exists():
                new_filename = f"{name_without_ext}_{counter}{ext}"
                new_abs_path = old_dir / new_filename
                counter += 1

        if abs_path.resolve() != new_abs_path.resolve():
            try:
                shutil.move(abs_path, new_abs_path)
                media_root = Path(media_root_str) if media_root_str else None
                try:
                    relative_path = new_abs_path.relative_to(media_root) if media_root else None
                    doc_instance.file_path = str(relative_path) if relative_path else str(new_abs_path)
                except ValueError:
                    doc_instance.file_path = str(new_abs_path)
                doc_instance.save(update_fields=["file_path"])
                logger.info("文件重命名成功: %s -> %s", raw_path, doc_instance.file_path)
            except Exception:
                logger.exception("文件重命名失败", extra={"raw_path": raw_path, "new_path": str(new_abs_path)})

    def get_identity_doc(self, doc_id: int) -> ClientIdentityDoc:
        """获取证件文档，不存在则抛出 NotFoundError"""

        doc = ClientIdentityDoc.objects.select_related("client").filter(id=doc_id).first()
        if not doc:
            raise NotFoundError(
                message=_("证件文档不存在"),
                code="IDENTITY_DOC_NOT_FOUND",
                errors={"doc_id": _("ID 为 %(id)s 的证件文档不存在") % {"id": doc_id}},
            )
        return doc

    def update_expiry_date(self, doc_id: int, expiry_date: date) -> None:
        """更新证件到期日期"""
        doc = self.get_identity_doc(doc_id)
        doc.expiry_date = expiry_date
        doc.save(update_fields=["expiry_date"])

    @transaction.atomic
    def upsert_identity_doc_file(self, *, client_id: int, doc_type: str, file_path: str) -> ClientIdentityDoc:
        """按 client+doc_type 更新或创建证件记录，并写入文件路径。"""
        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": _("ID 为 %(id)s 的当事人不存在") % {"id": client_id}},
            )

        doc, _created = ClientIdentityDoc.objects.get_or_create(client=client, doc_type=doc_type)
        if doc.file_path != file_path:
            doc.file_path = file_path
            doc.save(update_fields=["file_path"])
        return doc

    @transaction.atomic
    def delete_identity_doc(self, doc_id: int, user: Any) -> None:
        """删除证件文档及其磁盘文件。"""

        doc = self.get_identity_doc(doc_id)
        file_path = doc.file_path
        doc.delete()

        if file_path:
            transaction.on_commit(lambda fp=file_path: delete_media_file(fp))  # type: ignore[misc]

        logger.info("删除证件文档 %s", doc_id, extra={"user": user})

    def save_uploaded_file_to_dir(self, uploaded_file: Any, rel_dir: str) -> str:
        """保存上传文件到指定目录，返回相对路径（供 Admin Form 使用）"""

        rel_path, _ = save_uploaded_file(uploaded_file, rel_dir=rel_dir)
        return rel_path

    @transaction.atomic
    def add_identity_doc_from_upload(
        self,
        client_id: int,
        doc_type: str,
        uploaded_file: Any,
        user: Any = None,
    ) -> ClientIdentityDoc:
        """从上传文件添加当事人证件（文件 IO 在 Service 层处理）。"""
        saved_path: Path = self.file_upload_port.save_file(
            uploaded_file,
            base_dir=f"client_docs/{client_id}",
            preserve_name=True,
        )
        return self.add_identity_doc(
            client_id=client_id,
            doc_type=doc_type,
            file_path=str(saved_path),
            user=user,
        )
