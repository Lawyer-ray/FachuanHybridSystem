"""
客户 Admin 服务层
封装 Admin 层的复杂业务逻辑
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.core.exceptions import ValidationException
from ..models import Client, ClientIdentityDoc
import logging

User = get_user_model()
logger = logging.getLogger("apps.client")


@dataclass
class ImportResult:
    """JSON 导入结果"""
    success: bool
    client: Optional[Client] = None
    error_message: Optional[str] = None


class ClientAdminService:
    """
    客户 Admin 服务
    
    封装 Admin 层的复杂业务逻辑，确保 Admin 层方法保持在 20 行以内
    
    职责：
    1. 处理 JSON 数据导入
    2. 处理表单集文件上传
    3. 管理数据库事务
    4. 记录操作日志
    """
    
    def __init__(
        self,
        client_service: Optional["ClientService"] = None,
        identity_doc_service: Optional["ClientIdentityDocService"] = None
    ):
        """
        初始化服务
        
        Args:
            client_service: ClientService 实例，支持依赖注入
            identity_doc_service: ClientIdentityDocService 实例，支持依赖注入
        """
        self._client_service = client_service
        self._identity_doc_service = identity_doc_service
    
    @property
    def client_service(self) -> "ClientService":
        """延迟获取 ClientService"""
        if self._client_service is None:
            from .client_service import ClientService
            self._client_service = ClientService()
        return self._client_service
    
    @property
    def identity_doc_service(self) -> "ClientIdentityDocService":
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService
            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service
    
    @transaction.atomic
    def import_from_json(
        self,
        json_data: Dict[str, Any],
        admin_user: str
    ) -> ImportResult:
        """
        从 JSON 导入客户
        
        Args:
            json_data: JSON 数据字典
            admin_user: 管理员用户名
            
        Returns:
            ImportResult: 导入结果
            
        Raises:
            ValidationException: 数据验证失败
        """
        try:
            # 1. 验证 JSON 数据完整性
            self._validate_json_data(json_data)
            
            # 2. 提取客户基本信息
            client_data = self._extract_client_data(json_data)
            
            # 3. 创建客户
            client = Client.objects.create(**client_data)
            
            # 4. 创建关联的证件文档
            if 'identity_docs' in json_data:
                self._create_identity_docs(client, json_data['identity_docs'], admin_user)
            
            # 5. 记录操作日志
            logger.info(
                f"JSON 导入客户成功",
                extra={
                    "client_id": client.id,
                    "client_name": client.name,
                    "admin_user": admin_user,
                    "action": "import_from_json"
                }
            )
            
            return ImportResult(success=True, client=client)
            
        except ValidationException:
            # 重新抛出验证异常
            raise
        except Exception as e:
            # 记录错误日志
            logger.error(
                f"JSON 导入客户失败: {str(e)}",
                extra={
                    "admin_user": admin_user,
                    "action": "import_from_json",
                    "error": str(e)
                }
            )
            return ImportResult(
                success=False,
                error_message=f"导入失败: {str(e)}"
            )
    
    def _validate_json_data(self, json_data: Dict[str, Any]) -> None:
        """
        验证 JSON 数据完整性
        
        Args:
            json_data: JSON 数据字典
            
        Raises:
            ValidationException: 数据验证失败
        """
        errors = {}
        
        # 验证必填字段
        if not json_data.get('name'):
            errors['name'] = "客户名称不能为空"
        
        # 验证客户类型
        client_type = json_data.get('client_type')
        valid_types = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
        if not client_type or client_type not in valid_types:
            errors['client_type'] = f"客户类型必须是: {', '.join(valid_types)}"
        
        # 验证法人必须有法定代表人
        if client_type == Client.LEGAL and not json_data.get('legal_representative'):
            errors['legal_representative'] = "法人客户必须填写法定代表人"
        
        # 验证证件文档数据
        if 'identity_docs' in json_data:
            self._validate_identity_docs_data(json_data['identity_docs'], errors)
        
        if errors:
            raise ValidationException(
                message="JSON 数据验证失败",
                code="INVALID_JSON",
                errors=errors
            )
    
    def _validate_identity_docs_data(self, docs_data: List[Dict[str, Any]], errors: Dict[str, Any]) -> None:
        """
        验证证件文档数据
        
        Args:
            docs_data: 证件文档数据列表
            errors: 错误字典
        """
        if not isinstance(docs_data, list):
            errors['identity_docs'] = "证件文档数据必须是数组"
            return
        
        valid_doc_types = [choice[0] for choice in ClientIdentityDoc.DOC_TYPE_CHOICES]
        
        for i, doc_data in enumerate(docs_data):
            doc_errors = {}
            
            if not doc_data.get('doc_type'):
                doc_errors['doc_type'] = "证件类型不能为空"
            elif doc_data['doc_type'] not in valid_doc_types:
                doc_errors['doc_type'] = f"证件类型必须是: {', '.join(valid_doc_types)}"
            
            if not doc_data.get('file_path'):
                doc_errors['file_path'] = "文件路径不能为空"
            
            if doc_errors:
                errors[f'identity_docs[{i}]'] = doc_errors
    
    def _extract_client_data(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取客户基本信息
        
        Args:
            json_data: JSON 数据字典
            
        Returns:
            客户数据字典
        """
        client_fields = [
            'name', 'phone', 'address', 'client_type', 
            'id_number', 'legal_representative', 'is_our_client'
        ]
        
        client_data = {}
        for field in client_fields:
            if field in json_data:
                client_data[field] = json_data[field]
        
        # 设置默认值
        if 'is_our_client' not in client_data:
            client_data['is_our_client'] = False
        
        return client_data
    
    def _create_identity_docs(
        self, 
        client: Client, 
        docs_data: List[Dict[str, Any]], 
        admin_user: str
    ) -> None:
        """
        创建关联的证件文档
        
        Args:
            client: 客户对象
            docs_data: 证件文档数据列表
            admin_user: 管理员用户名
        """
        for doc_data in docs_data:
            self.identity_doc_service.add_identity_doc(
                client_id=client.id,
                doc_type=doc_data['doc_type'],
                file_path=doc_data['file_path'],
                user=None  # Admin 操作，用户信息在日志中记录
            )
    
    def process_formset_files(
        self,
        client_id: int,
        formset_data: List[Dict[str, Any]],
        admin_user: str
    ) -> None:
        """
        处理表单集文件上传
        
        Args:
            client_id: 客户 ID
            formset_data: 表单集数据列表
            admin_user: 管理员用户名
            
        Raises:
            ValidationException: 数据验证失败
        """
        try:
            # 1. 验证客户存在
            client = Client.objects.filter(id=client_id).first()
            if not client:
                raise ValidationException(
                    message="客户不存在",
                    code="CLIENT_NOT_FOUND",
                    errors={"client_id": f"ID 为 {client_id} 的客户不存在"}
                )
            
            # 2. 处理每个表单项
            processed_files = []
            for form_data in formset_data:
                if self._should_process_form(form_data):
                    file_info = self._process_single_form(client_id, form_data, admin_user)
                    if file_info:
                        processed_files.append(file_info)
            
            # 3. 记录操作日志
            logger.info(
                f"表单集文件处理完成",
                extra={
                    "client_id": client_id,
                    "processed_count": len(processed_files),
                    "admin_user": admin_user,
                    "action": "process_formset_files"
                }
            )
            
        except Exception as e:
            # 记录错误日志
            logger.error(
                f"表单集文件处理失败: {str(e)}",
                extra={
                    "client_id": client_id,
                    "admin_user": admin_user,
                    "action": "process_formset_files",
                    "error": str(e)
                }
            )
            raise
    
    def _should_process_form(self, form_data: Dict[str, Any]) -> bool:
        """
        判断是否应该处理该表单项
        
        Args:
            form_data: 表单数据
            
        Returns:
            是否应该处理
        """
        # 跳过标记为删除的项
        if form_data.get('DELETE'):
            return False
        
        # 必须有文件路径或上传的文件
        return bool(form_data.get('file_path') or form_data.get('uploaded_file'))
    
    def _process_single_form(
        self, 
        client_id: int, 
        form_data: Dict[str, Any], 
        admin_user: str
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个表单项
        
        Args:
            client_id: 客户 ID
            form_data: 表单数据
            admin_user: 管理员用户名
            
        Returns:
            处理后的文件信息，如果没有处理则返回 None
        """
        # 1. 获取证件类型
        doc_type = form_data.get('doc_type')
        if not doc_type:
            logger.warning(
                f"表单项缺少证件类型",
                extra={
                    "client_id": client_id,
                    "admin_user": admin_user,
                    "action": "process_single_form"
                }
            )
            return None
        
        # 2. 获取当事人名称和证件类型显示名
        client = Client.objects.filter(id=client_id).first()
        client_name = client.name if client else ""
        doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)
        
        # 3. 处理文件存储（传递当事人名称和证件类型用于重命名）
        file_path = self._handle_file_storage(form_data, client_name, doc_type_display)
        if not file_path:
            return None
        
        # 4. 更新或创建 ClientIdentityDoc 记录
        doc_id = form_data.get('id')
        if doc_id:
            # 更新现有记录
            self._update_identity_doc(doc_id, file_path, admin_user)
        else:
            # 创建新记录（直接创建，不调用 add_identity_doc 避免重复重命名）
            ClientIdentityDoc.objects.create(
                client_id=client_id,
                doc_type=doc_type,
                file_path=file_path
            )
        
        return {
            'doc_type': doc_type,
            'file_path': file_path,
            'doc_id': doc_id
        }
    
    def _handle_file_storage(self, form_data: Dict[str, Any], client_name: str = "", doc_type_display: str = "") -> Optional[str]:
        """
        处理文件存储
        
        Args:
            form_data: 表单数据
            client_name: 当事人名称
            doc_type_display: 证件类型显示名
            
        Returns:
            文件路径（相对路径），如果没有文件则返回 None
        """
        # 如果已有文件路径，直接使用
        if form_data.get('file_path'):
            return form_data['file_path']
        
        # 如果有上传的文件，处理文件存储
        uploaded_file = form_data.get('uploaded_file')
        if uploaded_file:
            return self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        
        return None
    
    def _save_uploaded_file(self, uploaded_file, client_name: str = "", doc_type: str = "") -> str:
        """
        保存上传的文件并重命名
        
        Args:
            uploaded_file: 上传的文件对象
            client_name: 当事人名称
            doc_type: 证件类型
            
        Returns:
            保存后的相对文件路径（相对于 MEDIA_ROOT）
        """
        import os
        from django.conf import settings
        
        if not hasattr(uploaded_file, 'name'):
            return ""
        
        # 创建目录
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'client_docs')
        os.makedirs(upload_dir, exist_ok=True)
        
        # 获取文件扩展名
        _, ext = os.path.splitext(uploaded_file.name)
        
        # 生成新文件名：当事人名称_证件类型.扩展名
        if client_name and doc_type:
            clean_name = self._sanitize_filename(client_name)
            clean_type = self._sanitize_filename(doc_type)
            new_filename = f"{clean_name}_{clean_type}{ext}"
        else:
            new_filename = uploaded_file.name
        
        # 处理重名文件
        file_path = os.path.join(upload_dir, new_filename)
        counter = 1
        base_name = os.path.splitext(new_filename)[0]
        while os.path.exists(file_path):
            new_filename = f"{base_name}_{counter}{ext}"
            file_path = os.path.join(upload_dir, new_filename)
            counter += 1
        
        # 保存文件
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # 返回相对路径（相对于 MEDIA_ROOT）
        return f"client_docs/{new_filename}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        filename = filename.strip(' .')
        if len(filename) > 50:
            filename = filename[:50]
        return filename or "未命名"
    
    def _update_identity_doc(self, doc_id: int, file_path: str, admin_user: str) -> None:
        """
        更新证件文档记录
        
        Args:
            doc_id: 证件文档 ID
            file_path: 新的文件路径
            admin_user: 管理员用户名
        """
        try:
            doc = ClientIdentityDoc.objects.get(id=doc_id)
            old_path = doc.file_path
            doc.file_path = file_path
            doc.save()
            
            # 记录更新日志
            logger.info(
                f"证件文档文件路径更新成功",
                extra={
                    "doc_id": doc_id,
                    "old_path": old_path,
                    "new_path": file_path,
                    "admin_user": admin_user,
                    "action": "update_identity_doc"
                }
            )
            
        except ClientIdentityDoc.DoesNotExist:
            logger.warning(
                f"尝试更新不存在的证件文档",
                extra={
                    "doc_id": doc_id,
                    "admin_user": admin_user,
                    "action": "update_identity_doc"
                }
            )
    def save_and_rename_file(
        self,
        client_id: int,
        client_name: str,
        doc_id: int,
        doc_type: str,
        uploaded_file
    ) -> str:
        """
        保存上传文件并重命名，更新数据库记录
        
        Args:
            client_id: 客户 ID
            client_name: 客户名称
            doc_id: 证件文档 ID
            doc_type: 证件类型
            uploaded_file: 上传的文件对象
            
        Returns:
            保存后的相对文件路径
        """
        # 获取证件类型显示名
        doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)
        
        # 保存文件并重命名
        file_path = self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        
        # 更新数据库记录
        if file_path:
            ClientIdentityDoc.objects.filter(id=doc_id).update(file_path=file_path)
            logger.info(
                f"证件文件保存成功",
                extra={
                    "client_id": client_id,
                    "doc_id": doc_id,
                    "file_path": file_path,
                    "action": "save_and_rename_file"
                }
            )
        
        return file_path

    def parse_client_text(self, text: str) -> Dict[str, Any]:
        """
        解析客户文本信息
        
        Args:
            text: 待解析的文本
            
        Returns:
            解析后的客户数据字典
        """
        from .text_parser import parse_client_text
        return parse_client_text(text)

    def parse_multiple_clients_text(self, text: str) -> List[Dict[str, Any]]:
        """
        解析包含多个客户的文本信息
        
        Args:
            text: 待解析的文本
            
        Returns:
            解析后的客户数据列表
        """
        from .text_parser import parse_multiple_clients_text
        return parse_multiple_clients_text(text)