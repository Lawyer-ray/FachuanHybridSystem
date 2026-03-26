"""案件文件夹扫描 API Schemas。"""

from __future__ import annotations

from ninja import Schema
from pydantic import Field


class CaseFolderScanStartIn(Schema):
    rescan: bool = False
    scan_subfolder: str = ""
    enable_recognition: bool = False


class CaseFolderScanStartOut(Schema):
    session_id: str
    status: str
    task_id: str = ""


class CaseFolderScanSubfolderOptionOut(Schema):
    relative_path: str
    display_name: str


class CaseFolderScanSubfolderListOut(Schema):
    root_path: str
    subfolders: list[CaseFolderScanSubfolderOptionOut]


class CaseFolderScanSummaryOut(Schema):
    total_files: int = 0
    deduped_files: int = 0
    classified_files: int = 0


class CaseFolderScanCandidateOut(Schema):
    source_path: str
    filename: str
    file_size: int
    modified_at: str
    base_name: str
    version_token: str
    extract_method: str
    text_excerpt: str
    suggested_category: str = "unknown"
    suggested_side: str = "unknown"
    type_name_hint: str = ""
    suggested_supervising_authority_id: int | None = None
    suggested_party_ids: list[int] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    selected: bool = True


class CaseFolderScanPrefillOut(Schema):
    category: str = ""
    side: str = ""
    type_name_hint: str = ""
    supervising_authority_id: int | None = None
    party_ids: list[int] = Field(default_factory=list)


class CaseFolderScanStatusOut(Schema):
    session_id: str
    status: str
    progress: int
    current_file: str = ""
    scan_subfolder: str = ""
    enable_recognition: bool = False
    summary: CaseFolderScanSummaryOut
    candidates: list[CaseFolderScanCandidateOut]
    error_message: str = ""
    prefill_map: dict[str, CaseFolderScanPrefillOut] = Field(default_factory=dict)


class CaseFolderScanStageItemIn(Schema):
    source_path: str
    selected: bool = True
    category: str = "unknown"
    side: str = "unknown"
    type_name_hint: str = ""
    supervising_authority_id: int | None = None
    party_ids: list[int] = Field(default_factory=list)


class CaseFolderScanStageIn(Schema):
    items: list[CaseFolderScanStageItemIn]


class CaseFolderScanStageOut(Schema):
    session_id: str
    status: str
    log_id: int
    attachment_ids: list[int]
    materials_url: str
    prefill_map: dict[str, CaseFolderScanPrefillOut] = Field(default_factory=dict)


__all__ = [
    "CaseFolderScanStartIn",
    "CaseFolderScanStartOut",
    "CaseFolderScanSubfolderOptionOut",
    "CaseFolderScanSubfolderListOut",
    "CaseFolderScanSummaryOut",
    "CaseFolderScanCandidateOut",
    "CaseFolderScanPrefillOut",
    "CaseFolderScanStatusOut",
    "CaseFolderScanStageItemIn",
    "CaseFolderScanStageIn",
    "CaseFolderScanStageOut",
]
