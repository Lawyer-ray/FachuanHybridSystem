"""当事人证件文档服务。"""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.storage import _get_media_root, delete_media_file, sanitize_upload_filename, save_uploaded_file


logger = logging.getLogger("apps.client")


class ClientIdentityDocService:
    """当事人证件服务"""

    @transaction.atomic
    def add_identity_doc(self, client_id: int, doc_type: str, file_path: str, user: Any = None) -> ClientIdentityDoc:
        """添加当事人证件"""

        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": str(_("ID 为 %(id)s 的当事人不存在") % {"id": client_id})},
            )

        # 创建证件记录
        doc = ClientIdentityDoc.objects.create(client=client, doc_type=doc_type, file_path=file_path)

        # 重命名文件（对所有非空路径执行），在事务提交后执行文件系统操作
        if file_path:
            transaction.on_commit(lambda doc_id=doc.pk: self._rename_uploaded_file_by_id(doc_id))

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
        # 相对路径通过 MEDIA_ROOT 解析为绝对路径
        p = Path(raw_path)
        if not p.is_absolute():
            media_root_str = _get_media_root()
            abs_path = Path(media_root_str) / p if media_root_str else p
        else:
            abs_path = p

        if not abs_path.exists():
            return

        # 获取文件扩展名
        ext = abs_path.suffix

        # 生成新文件名：{doc_type}（{client_name}）.ext
        client_name = sanitize_upload_filename(doc_instance.client.name)
        doc_type_display = doc_instance.get_doc_type_display()
        new_filename = f"{doc_type_display}（{client_name}）{ext}"

        # 生成新路径
        old_dir = abs_path.parent
        new_abs_path = old_dir / new_filename

        # 如果新路径已存在且不是同一文件，添加序号
        if new_abs_path.exists() and abs_path.resolve() != new_abs_path.resolve():
            counter = 1
            name_without_ext = f"{doc_type_display}（{client_name}）"
            while new_abs_path.exists():
                new_filename = f"{name_without_ext}_{counter}{ext}"
                new_abs_path = old_dir / new_filename
                counter += 1

        # 重命名文件
        if abs_path.resolve() != new_abs_path.resolve():
            try:
                shutil.move(abs_path, new_abs_path)
                # 保存相对路径（相对于 MEDIA_ROOT）
                media_root_str = _get_media_root()
                media_root = Path(media_root_str) if media_root_str else None
                try:
                    relative_path = new_abs_path.relative_to(media_root) if media_root else None
                    doc_instance.file_path = str(relative_path) if relative_path else str(new_abs_path)
                except ValueError:
                    # 不在 MEDIA_ROOT 下时保存绝对路径
                    doc_instance.file_path = str(new_abs_path)
                doc_instance.save(update_fields=["file_path"])
                logger.info("文件重命名成功: %s -> %s", raw_path, doc_instance.file_path)
            except Exception as e:
                raise ValidationException(
                    message=_("文件重命名失败"),
                    code="FILE_RENAME_ERROR",
                    errors={"file": str(e)},
                ) from e

    def get_identity_doc(self, doc_id: int) -> ClientIdentityDoc:
        """获取证件文档，不存在则抛出 NotFoundError"""

        doc = ClientIdentityDoc.objects.select_related("client").filter(id=doc_id).first()
        if not doc:
            raise NotFoundError(
                message=_("证件文档不存在"),
                code="IDENTITY_DOC_NOT_FOUND",
                errors={"doc_id": str(_("ID 为 %(id)s 的证件文档不存在") % {"id": doc_id})},
            )
        return doc

    def update_expiry_date(self, doc_id: int, expiry_date: date) -> None:
        """更新证件到期日期"""
        doc = self.get_identity_doc(doc_id)
        doc.expiry_date = expiry_date
        doc.save(update_fields=["expiry_date"])

    @transaction.atomic
    def delete_identity_doc(self, doc_id: int, user: Any) -> None:
        """删除证件文档及其磁盘文件。"""

        doc = self.get_identity_doc(doc_id)
        file_path = doc.file_path
        doc.delete()

        if file_path:
            transaction.on_commit(lambda fp=file_path: delete_media_file(fp))

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
        """从上传文件添加当事人证件（文件 IO 在 Service 层处理）"""
        from apps.core.services.file_upload_service import FileUploadService

        upload_service = FileUploadService()
        saved_path: Path = upload_service.save_file(
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
