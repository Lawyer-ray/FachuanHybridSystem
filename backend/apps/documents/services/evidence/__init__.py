import importlib
from typing import Any

# (module_name, attr_name)
_IMPORT_MAP: dict[str, tuple[str, str]] = {
    "EvidenceFileService": ("evidence_file_service", "EvidenceFileService"),
    "EvidenceMutationService": ("evidence_mutation_service", "EvidenceMutationService"),
    "EvidenceBasicQueryService": ("evidence_query_service", "EvidenceQueryService"),
    "EvidenceService": ("evidence_service", "EvidenceService"),
    "EvidenceAdminService": ("evidence_admin_service", "EvidenceAdminService"),
    "EvidenceExportService": ("evidence_export_service", "EvidenceExportService"),
    "EvidenceListPlaceholderService": ("evidence_list_placeholder_service", "EvidenceListPlaceholderService"),
    "EvidencePageRangeCalculator": ("page_range_calculator", "EvidencePageRangeCalculator"),
    "evidence_file_storage": ("evidence_storage", "evidence_file_storage"),
}


def __getattr__(name: str) -> Any:
    """延迟导入避免循环依赖"""
    entry = _IMPORT_MAP.get(name)
    if entry is not None:
        module_path, attr_name = entry
        module = importlib.import_module(f".{module_path}", __name__)
        return getattr(module, attr_name)
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
