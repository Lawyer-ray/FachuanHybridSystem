"""文件模板初始化服务"""

import logging
from typing import Any

from django.db import transaction

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderTemplate

from .complete_defaults import get_complete_default_data
from .default_templates import DEFAULT_DOCUMENT_TEMPLATES

logger = logging.getLogger(__name__)


class DocumentTemplateInitService:
    """文件模板初始化服务"""

    @transaction.atomic
    def initialize_default_templates(self) -> dict[str, Any]:
        """
        初始化默认文件模板（完整版）
        
        包含：
        1. 文件夹模板
        2. 文件模板
        3. 文件模板与文件夹的绑定关系
        
        Returns:
            包含各项创建和跳过数量的字典
        """
        data = get_complete_default_data()
        
        folder_created = 0
        folder_skipped = 0
        doc_created = 0
        doc_skipped = 0
        binding_created = 0
        binding_skipped = 0
        
        # 1. 初始化文件夹模板
        folder_map: dict[str, Any] = {}
        for folder_data in data["folder_templates"]:
            existing = FolderTemplate.objects.filter(name=folder_data["name"]).first()
            if existing:
                logger.info(f"跳过已存在的文件夹模板: {folder_data['name']}")
                folder_skipped += 1
                folder_map[folder_data["name"]] = existing
            else:
                folder = FolderTemplate.objects.create(**folder_data)
                logger.info(f"创建文件夹模板: {folder_data['name']}")
                folder_created += 1
                folder_map[folder_data["name"]] = folder
        
        # 2. 初始化文件模板
        doc_map: dict[str, Any] = {}
        for template_data in data["document_templates"]:
            existing_doc = DocumentTemplate.objects.filter(
                name=template_data["name"], template_type=template_data["template_type"]
            ).first()
            if existing_doc:
                logger.info(f"跳过已存在的文件模板: {template_data['name']}")
                doc_skipped += 1
                doc_map[template_data["name"]] = existing_doc
            else:
                doc = DocumentTemplate.objects.create(**template_data)
                logger.info(f"创建文件模板: {template_data['name']}")
                doc_created += 1
                doc_map[template_data["name"]] = doc
        
        # 3. 初始化绑定关系
        for binding_data in data["bindings"]:
            doc_name = binding_data["document_template_name"]
            folder_name = binding_data["folder_template_name"]
            node_id = binding_data["folder_node_id"]
            
            if doc_name not in doc_map or folder_name not in folder_map:
                logger.warning(f"跳过绑定（模板不存在）: {doc_name} -> {folder_name}")
                continue
            
            doc = doc_map[doc_name]
            folder = folder_map[folder_name]
            
            existing_binding = DocumentTemplateFolderBinding.objects.filter(
                document_template=doc, folder_template=folder, folder_node_id=node_id
            ).exists()
            
            if existing_binding:
                logger.info(f"跳过已存在的绑定: {doc_name} -> {folder_name}")
                binding_skipped += 1
            else:
                # 计算文件夹路径
                from apps.documents.services.contract_template_binding_service import (
                    DocumentTemplateBindingService,
                )

                binding_service = DocumentTemplateBindingService()
                folder_node_path = binding_service.calculate_folder_path(folder, node_id)

                DocumentTemplateFolderBinding.objects.create(
                    document_template=doc,
                    folder_template=folder,
                    folder_node_id=node_id,
                    folder_node_path=folder_node_path,
                )
                logger.info(f"创建绑定: {doc_name} -> {folder_name} (路径: {folder_node_path})")
                binding_created += 1
        
        return {
            "folder_created": folder_created,
            "folder_skipped": folder_skipped,
            "doc_created": doc_created,
            "doc_skipped": doc_skipped,
            "binding_created": binding_created,
            "binding_skipped": binding_skipped,
        }
