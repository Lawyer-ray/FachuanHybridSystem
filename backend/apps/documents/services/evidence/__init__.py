def __getattr__(name: str):
    """延迟导入避免循环依赖"""
    if name == "EvidenceFileService":
        from .evidence_file_service import EvidenceFileService

        return EvidenceFileService
    elif name == "EvidenceMutationService":
        from .evidence_mutation_service import EvidenceMutationService

        return EvidenceMutationService
    elif name == "EvidenceBasicQueryService":
        from .evidence_query_service import EvidenceQueryService

        return EvidenceQueryService
    elif name == "EvidenceService":
        from .evidence_service import EvidenceService

        return EvidenceService
    elif name == "EvidenceAdminService":
        from .evidence_admin_service import EvidenceAdminService

        return EvidenceAdminService
    elif name == "EvidenceExportService":
        from .evidence_export_service import EvidenceExportService

        return EvidenceExportService
    elif name == "EvidenceListPlaceholderService":
        from .evidence_list_placeholder_service import EvidenceListPlaceholderService

        return EvidenceListPlaceholderService
    elif name == "EvidencePageRangeCalculator":
        from .page_range_calculator import EvidencePageRangeCalculator

        return EvidencePageRangeCalculator
    elif name == "evidence_file_storage":
        from .evidence_storage import evidence_file_storage

        return evidence_file_storage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EvidenceFileService",
    "EvidenceMutationService",
    "EvidenceBasicQueryService",
    "EvidenceService",
    "EvidenceAdminService",
    "EvidenceExportService",
    "EvidenceListPlaceholderService",
    "EvidencePageRangeCalculator",
    "evidence_file_storage",
]
