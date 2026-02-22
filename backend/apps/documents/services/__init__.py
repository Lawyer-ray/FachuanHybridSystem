"""
Documents Services 模块

包含所有文书生成相关的业务逻辑服务.
"""

import importlib
from typing import Any

__all__ = [
    "FolderTemplateService",
    "DocumentTemplateService",
    "PlaceholderService",
    "PlaceholderAdminService",
    "GenerationService",
    "ContractGenerationService",
    # 证据清单服务
    "EvidenceService",
    "EvidenceAdminService",
    "EvidenceExportService",
    "EvidenceListPlaceholderService",
    "PDFMergeService",
    "TemplateAuditLogService",
]


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "EvidenceAdminService": ("apps.documents.services.evidence_admin_service", "EvidenceAdminService"),
    "EvidenceExportService": ("apps.documents.services.evidence_export_service", "EvidenceExportService"),
    "EvidenceListPlaceholderService": (
        "apps.documents.services.evidence_list_placeholder_service",
        "EvidenceListPlaceholderService",
    ),
    "EvidenceService": ("apps.documents.services.evidence_service", "EvidenceService"),
    "FolderTemplateService": ("apps.documents.services.folder_service", "FolderTemplateService"),
    "ContractGenerationService": (
        "apps.documents.services.generation.contract_generation_service",
        "ContractGenerationService",
    ),
    "GenerationService": ("apps.documents.services.generation_service", "GenerationService"),
    "PDFMergeService": ("apps.documents.services.pdf_merge_service", "PDFMergeService"),
    "PlaceholderAdminService": ("apps.documents.services.placeholder_admin_service", "PlaceholderAdminService"),
    "PlaceholderService": ("apps.documents.services.placeholder_service", "PlaceholderService"),
    "DocumentTemplateService": ("apps.documents.services.template_service", "DocumentTemplateService"),
    "TemplateAuditLogService": (
        "apps.documents.services.template_audit_log_service",
        "TemplateAuditLogService",
    ),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__) | set(_LAZY_EXPORTS.keys()))
