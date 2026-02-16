import os
import shutil
import logging
from django.conf import settings
from django.db import transaction
from apps.core.exceptions import ValidationException, NotFoundError

logger = logging.getLogger("apps.client")


class ClientIdentityDocService:
    """当事人证件服务"""

    @transaction.atomic
    def add_identity_doc(self, client_id: int, doc_type: str, file_path: str, user=None):
        """添加当事人证件"""
        from ..models import ClientIdentityDoc, Client
        
        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise NotFoundError(
                message="当事人不存在",
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"}
            )
        
        # 创建证件记录
        doc = ClientIdentityDoc.objects.create(
            client=client,
            doc_type=doc_type,
            file_path=file_path
        )
        
        # 重命名文件（仅当文件路径是绝对路径时）
        if file_path and os.path.isabs(file_path):
            self.rename_uploaded_file(doc)
        
        return doc

    def rename_uploaded_file(self, doc_instance):
        """重命名上传的文件"""
        if not doc_instance.file_path or not doc_instance.client:
            return
            
        old_path = doc_instance.file_path
        if not os.path.exists(old_path):
            return
            
        # 获取文件扩展名
        _, ext = os.path.splitext(old_path)
        
        # 生成新文件名：当事人名称_证件类型.扩展名
        client_name = self._sanitize_filename(doc_instance.client.name)
        doc_type_display = doc_instance.get_doc_type_display()
        new_filename = f"{client_name}_{doc_type_display}{ext}"
        
        # 生成新路径
        old_dir = os.path.dirname(old_path)
        new_path = os.path.join(old_dir, new_filename)
        
        # 如果新路径已存在且不是同一文件，添加序号
        if os.path.exists(new_path) and os.path.abspath(old_path) != os.path.abspath(new_path):
            counter = 1
            name_without_ext = f"{client_name}_{doc_type_display}"
            while os.path.exists(new_path):
                new_filename = f"{name_without_ext}_{counter}{ext}"
                new_path = os.path.join(old_dir, new_filename)
                counter += 1
        
        # 重命名文件
        if os.path.abspath(old_path) != os.path.abspath(new_path):
            try:
                shutil.move(old_path, new_path)
                doc_instance.file_path = new_path
                doc_instance.save(update_fields=['file_path'])
            except Exception as e:
                raise ValidationException(f"文件重命名失败: {str(e)}", code="FILE_RENAME_ERROR")
    
    def _sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        # 替换文件名中的非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # 移除首尾空格和点
        filename = filename.strip(' .')
        
        # 限制长度
        if len(filename) > 50:
            filename = filename[:50]
            
        return filename or "未命名"