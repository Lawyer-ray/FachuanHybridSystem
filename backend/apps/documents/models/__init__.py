"""
法律文书生成系统数据模型

本模块定义文书生成系统的核心数据模型:
- FolderTemplate: 文件夹模板
- DocumentTemplate: 文件模板
- Placeholder: 替换词
- TemplateAuditLog: 模板审计日志
- EvidenceList: 证据清单
- EvidenceItem: 证据明细
"""

from __future__ import annotations

from .audit_log import TemplateAuditLog

# 导入所有选项类
from .choices import (
    DocumentCaseFileSubType,
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractSubType,
    DocumentContractType,
    DocumentTemplateType,
    FillType,
    FolderTemplateType,
    LegalStatusMatchMode,
    PlaceholderCategory,
    PlaceholderFormatType,
    SourceType,
    TemplateAuditAction,
    TemplateCategory,
    TemplateStatus,
)
from .document_template import DocumentTemplate, DocumentTemplateFolderBinding
from .evidence import LIST_TYPE_ORDER, LIST_TYPE_PREVIOUS, EvidenceItem, EvidenceList, ListType, MergeStatus
from .external_template import ExternalTemplate, ExternalTemplateFieldMapping
from .fill_record import BatchFillTask, FillRecord

# 导入所有模型类
from .folder_template import FolderTemplate
from .generation import GenerationConfig, GenerationMethod, GenerationStatus, GenerationTask
from .placeholder import Placeholder
from .prompt_version import PromptVersion
from .proxy_matter_rule import ProxyMatterRule

# 统一导出
__all__ = [
    # 选项类
    "DocumentCaseType",
    "DocumentCaseStage",
    "DocumentContractType",
    "FolderTemplateType",
    "DocumentTemplateType",
    "DocumentContractSubType",
    "DocumentCaseFileSubType",
    "PlaceholderCategory",
    "PlaceholderFormatType",
    "TemplateAuditAction",
    # 模型类
    "FolderTemplate",
    "DocumentTemplate",
    "DocumentTemplateFolderBinding",
    "Placeholder",
    "TemplateAuditLog",
    # 证据清单模型
    "EvidenceList",
    "EvidenceItem",
    "MergeStatus",
    "ListType",
    "LIST_TYPE_PREVIOUS",
    "LIST_TYPE_ORDER",
    # Prompt 版本管理
    "PromptVersion",
    # 文书生成
    "GenerationTask",
    "GenerationConfig",
    "GenerationMethod",
    "GenerationStatus",
    # 授权委托书
    "ProxyMatterRule",
    # 诉讼地位匹配
    "LegalStatusMatchMode",
    # 外部模板枚举
    "TemplateCategory",
    "SourceType",
    "FillType",
    "TemplateStatus",
    # 外部模板模型
    "ExternalTemplate",
    "ExternalTemplateFieldMapping",
    "BatchFillTask",
    "FillRecord",
]

GenerationTaskStatus = GenerationStatus
