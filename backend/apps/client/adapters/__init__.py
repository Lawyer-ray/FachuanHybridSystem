"""Client 模块适配器实现。"""

from __future__ import annotations

from .admin_adapters import CredentialAdapter, GsxtReportAdapter
from .file_upload_adapter import FileUploadAdapter
from .file_validator_adapter import FileValidatorAdapter
from .task_service_adapter import TaskServiceAdapter

__all__ = [
    "CredentialAdapter",
    "FileUploadAdapter",
    "FileValidatorAdapter",
    "GsxtReportAdapter",
    "TaskServiceAdapter",
]
