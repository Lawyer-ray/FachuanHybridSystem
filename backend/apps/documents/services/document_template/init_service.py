"""文件模板初始化服务"""

import logging
from typing import Any

from django.db import transaction

from apps.documents.models import DocumentTemplate
from .default_templates import DEFAULT_DOCUMENT_TEMPLATES

logger = logging.getLogger(__name__)


class DocumentTemplateInitService:
    """文件模板初始化服务"""

    @transaction.atomic
    def initialize_default_templates(self) -> dict[str, Any]:
        """
        初始化默认文件模板
        
        Returns:
            包含created和skipped数量的字典
        """
        created_count = 0
        skipped_count = 0
        
        for template_data in DEFAULT_DOCUMENT_TEMPLATES:
            # 检查是否已存在同名模板
            exists = DocumentTemplate.objects.filter(
                name=template_data["name"],
                template_type=template_data["template_type"]
            ).exists()
            
            if exists:
                logger.info(f"跳过已存在的模板: {template_data['name']}")
                skipped_count += 1
                continue
            
            # 创建新模板
            DocumentTemplate.objects.create(**template_data)
            logger.info(f"创建模板: {template_data['name']}")
            created_count += 1
        
        return {
            "created": created_count,
            "skipped": skipped_count,
            "total": len(DEFAULT_DOCUMENT_TEMPLATES)
        }
