def __getattr__(name: str) -> type:
    """延迟导入避免循环依赖"""
    _map: dict[str, tuple[str, str]] = {
        "EvidenceFileService": (".evidence_file_service", "EvidenceFileService"),
        "EvidenceMutationService": (".evidence_mutation_service", "EvidenceMutationService"),
        "EvidenceBasicQueryService": (".evidence_query_service", "EvidenceQueryService"),
        "EvidenceQueryService": (".evidence_query_service", "EvidenceQueryService"),
        "EvidenceService": (".evidence_service", "EvidenceService"),
        "EvidenceAdminService": (".evidence_admin_service", "EvidenceAdminService"),
        "EvidenceExportService": (".evidence_export_service", "EvidenceExportService"),
        "EvidenceListPlaceholderService": (".evidence_list_placeholder_service", "EvidenceListPlaceholderService"),
        "EvidencePageRangeCalculator": (".page_range_calculator", "EvidencePageRangeCalculator"),
        "evidence_file_storage": (".evidence_storage", "evidence_file_storage"),
        "EvidenceAIService": (".evidence_ai_service", "EvidenceAIService"),
        "EvidenceOCRService": (".evidence_ocr_service", "EvidenceOCRService"),
        "EvidenceSearchService": (".evidence_ocr_service", "EvidenceSearchService"),
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
