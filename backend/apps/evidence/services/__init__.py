from typing import Any


def __getattr__(name: str) -> Any:
    """延迟导入避免循环依赖"""
    _map: dict[str, tuple[str, str]] = {
        "EvidenceFileService": (".core.evidence_file_service", "EvidenceFileService"),
        "EvidenceMutationService": (".mutation.evidence_mutation_service", "EvidenceMutationService"),
        "EvidenceBasicQueryService": (".core.evidence_query_service", "EvidenceQueryService"),
        "EvidenceQueryService": (".core.evidence_query_service", "EvidenceQueryService"),
        "EvidenceService": (".core.evidence_service", "EvidenceService"),
        "EvidenceAdminService": (".admin.evidence_admin_service", "EvidenceAdminService"),
        "EvidenceExportService": (".export.evidence_export_service", "EvidenceExportService"),
        "EvidenceListPlaceholderService": (".admin.evidence_list_placeholder_service", "EvidenceListPlaceholderService"),
        "EvidencePageRangeCalculator": (".core.page_range_calculator", "EvidencePageRangeCalculator"),
        "evidence_file_storage": (".core.evidence_storage", "evidence_file_storage"),
        "EvidenceAIService": (".ai.evidence_ai_service", "EvidenceAIService"),
        "EvidenceOCRService": (".ai.evidence_ocr_service", "EvidenceOCRService"),
        "EvidenceSearchService": (".ai.evidence_ocr_service", "EvidenceSearchService"),
    }
    if name in _map:
        import importlib

        mod_path, attr_name = _map[name]
        mod = importlib.import_module(mod_path, __package__)
        return getattr(mod, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EvidenceFileService",
    "EvidenceMutationService",
    "EvidenceBasicQueryService",
    "EvidenceQueryService",
    "EvidenceService",
    "EvidenceAdminService",
    "EvidenceExportService",
    "EvidenceListPlaceholderService",
    "EvidencePageRangeCalculator",
    "evidence_file_storage",
    "EvidenceAIService",
    "EvidenceOCRService",
    "EvidenceSearchService",
]
