from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
import shutil
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.client.services.storage import sanitize_upload_filename

logger = logging.getLogger("apps.client")


class ClientIdentityDocService:
    """当事人证件服务"""

    @transaction.atomic
    def add_identity_doc(self, client_id: int, doc_type: str, file_path: str, user: Any = None) -> Any:
        """添加当事人证件"""
        from apps.client.models import Client, ClientIdentityDoc

        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"},
            )

        # 创建证件记录
        doc = ClientIdentityDoc.objects.create(client=client, doc_type=doc_type, file_path=file_path)

        # 重命名文件（对所有非空路径执行）
        if file_path:
            self.rename_uploaded_file(doc)

        return doc

    def rename_uploaded_file(self, doc_instance: Any) -> None:
        """重命名上传的文件"""
        if not doc_instance.file_path or not doc_instance.client:
            return

        raw_path = doc_instance.file_path
        # 相对路径通过 MEDIA_ROOT 解析为绝对路径
        p = Path(raw_path)
        if not p.is_absolute():
            media_root = Path(settings.MEDIA_ROOT)
            abs_path = media_root / p
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
                shutil.move(str(abs_path), str(new_abs_path))
                # 保存相对路径（相对于 MEDIA_ROOT）
                media_root = Path(settings.MEDIA_ROOT)
                try:
                    relative_path = new_abs_path.relative_to(media_root)
                    doc_instance.file_path = str(relative_path)
                except ValueError:
                    # 不在 MEDIA_ROOT 下时保存绝对路径
                    doc_instance.file_path = str(new_abs_path)
                doc_instance.save(update_fields=["file_path"])
                logger.info("文件重命名成功: %s -> %s", raw_path, doc_instance.file_path)
            except Exception as e:
                raise ValidationException(f"文件重命名失败: {e!s}", code="FILE_RENAME_ERROR") from e

    @transaction.atomic
    def add_identity_doc_from_upload(
        self,
        client_id: int,
        doc_type: str,
        uploaded_file: Any,
        user: Any = None,
    ) -> Any:
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
