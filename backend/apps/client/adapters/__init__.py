"""Client 模块适配器实现。"""

from __future__ import annotations

from .admin_adapters import ConflictCheckAdapter, CredentialAdapter, GsxtReportAdapter
from .file_upload_adapter import FileUploadAdapter
from .file_validator_adapter import FileValidatorAdapter
from .related_items_adapter import RelatedItemsAdapter
from .task_service_adapter import TaskServiceAdapter

__all__ = [
    "ConflictCheckAdapter",
    "CredentialAdapter",
    "FileUploadAdapter",
    "FileValidatorAdapter",
    "GsxtReportAdapter",
    "RelatedItemsAdapter",
    "TaskServiceAdapter",
]
