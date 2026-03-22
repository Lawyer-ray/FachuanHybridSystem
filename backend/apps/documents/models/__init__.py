"""
法律文书生成系统数据模型

本模块定义文书生成系统的核心数据模型.
证据清单模型已迁移到 apps.evidence，此处通过 __getattr__ 保留向后兼容.
"""

from __future__ import annotations

import importlib as _importlib
from typing import Any

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
from .external_template import ExternalTemplate, ExternalTemplateFieldMapping
from .fill_record import BatchFillTask, FillRecord

# 导入所有模型类
from .folder_template import FolderTemplate
from .generation import GenerationConfig, GenerationMethod, GenerationStatus, GenerationTask
from .placeholder import Placeholder
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
    # 证据清单模型（向后兼容，实际定义在 apps.evidence）
    "EvidenceList",
    "EvidenceItem",
    "MergeStatus",
    "ListType",
    "LIST_TYPE_PREVIOUS",
    "LIST_TYPE_ORDER",
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

# 证据清单模型已迁移到 apps.evidence，延迟导入避免循环依赖
_EVIDENCE_NAMES = frozenset(
    {
        "LIST_TYPE_ORDER",
        "LIST_TYPE_PREVIOUS",
        "EvidenceItem",
        "EvidenceList",
        "ListType",
        "MergeStatus",
    }
)


def __getattr__(name: str) -> Any:
    if name in _EVIDENCE_NAMES:
        _mod = _importlib.import_module("apps.evidence.models")
        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
