"""Client 模块端口定义。"""

from __future__ import annotations

from .admin_ports import ConflictCheckPort, CredentialPort, GsxtReportPort
from .file_upload_port import FileUploadPort
from .file_validator_port import FileValidatorPort
from .related_items_port import RelatedItemsPort
from .task_service_port import TaskServicePort

__all__ = [
    "ConflictCheckPort",
    "CredentialPort",
    "FileUploadPort",
    "FileValidatorPort",
    "GsxtReportPort",
    "RelatedItemsPort",
    "TaskServicePort",
]
