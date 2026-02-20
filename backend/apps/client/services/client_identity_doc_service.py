from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
import shutil
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException

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

        # 重命名文件（仅当文件路径是绝对路径时）
        if file_path and Path(file_path).is_absolute():
            self.rename_uploaded_file(doc)

        return doc

    def rename_uploaded_file(self, doc_instance: Any) -> None:
        """重命名上传的文件"""
        if not doc_instance.file_path or not doc_instance.client:
            return

        old_path = doc_instance.file_path
        if not Path(old_path).exists():
            return

        # 获取文件扩展名
        ext = Path(old_path).suffix

        # 生成新文件名：当事人名称_证件类型.扩展名
        client_name = self._sanitize_filename(doc_instance.client.name)
        doc_type_display = doc_instance.get_doc_type_display()
        new_filename = f"{client_name}_{doc_type_display}{ext}"

        # 生成新路径
        old_dir = Path(old_path).parent
        new_path = old_dir / new_filename

        # 如果新路径已存在且不是同一文件，添加序号
        if new_path.exists() and Path(old_path).resolve() != new_path.resolve():
            counter = 1
            name_without_ext = f"{client_name}_{doc_type_display}"
            while new_path.exists():
                new_filename = f"{name_without_ext}_{counter}{ext}"
                new_path = old_dir / new_filename
                counter += 1

        # 重命名文件
        if Path(old_path).resolve() != new_path.resolve():
            try:
                shutil.move(old_path, str(new_path))
                doc_instance.file_path = str(new_path)
                doc_instance.save(update_fields=["file_path"])
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

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 替换文件名中的非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # 移除首尾空格和点
        filename = filename.strip(" .")

        # 限制长度
        if len(filename) > 50:
            filename = filename[:50]

        return filename or "未命名"
