"""合同文件夹扫描 API Schemas。"""

from __future__ import annotations

from ninja import Schema


class ContractFolderScanStartIn(Schema):
    rescan: bool = False
    scan_subfolder: str = ""


class ContractFolderScanStartOut(Schema):
    session_id: str
    status: str
    task_id: str = ""


class ContractFolderScanSubfolderOptionOut(Schema):
    relative_path: str
    display_name: str


class ContractFolderScanSubfolderListOut(Schema):
    root_path: str
    subfolders: list[ContractFolderScanSubfolderOptionOut]


class ContractFolderScanSummaryOut(Schema):
    total_files: int = 0
    deduped_files: int = 0
    classified_files: int = 0


class ContractFolderScanCandidateOut(Schema):
    source_path: str
    filename: str
    file_size: int
    modified_at: str
    base_name: str
    version_token: str
    extract_method: str
    text_excerpt: str
    suggested_category: str = "archive_document"
    confidence: float = 0.0
    reason: str = ""
    selected: bool = True
    archive_item_code: str = ""
    archive_item_name: str = ""
    is_docx: bool = False
    skip_reason: str = ""
    already_imported: bool = False


class ArchiveItemOptionOut(Schema):
    code: str
    name: str


class WorkLogSuggestionOut(Schema):
    date: str
    content: str


class ContractFolderScanStatusOut(Schema):
    session_id: str
    status: str
    progress: int
    current_file: str = ""
    summary: ContractFolderScanSummaryOut
    candidates: list[ContractFolderScanCandidateOut]
    error_message: str = ""
    archive_category: str = ""
    archive_item_options: list[ArchiveItemOptionOut] = []
    work_log_suggestions: list[WorkLogSuggestionOut] = []


class ContractFolderScanConfirmItemIn(Schema):
    source_path: str
    selected: bool = True
    category: str
    archive_item_code: str = ""
    is_docx: bool = False


class ContractFolderScanConfirmIn(Schema):
    items: list[ContractFolderScanConfirmItemIn]
    work_log_suggestions: list[WorkLogSuggestionOut] = []


class ContractFolderScanConfirmOut(Schema):
    session_id: str
    status: str
    imported_count: int


__all__ = [
    "ContractFolderScanStartIn",
    "ContractFolderScanStartOut",
    "ContractFolderScanSubfolderOptionOut",
    "ContractFolderScanSubfolderListOut",
    "ContractFolderScanSummaryOut",
    "ContractFolderScanCandidateOut",
    "ArchiveItemOptionOut",
    "WorkLogSuggestionOut",
    "ContractFolderScanStatusOut",
    "ContractFolderScanConfirmItemIn",
    "ContractFolderScanConfirmIn",
    "ContractFolderScanConfirmOut",
]
