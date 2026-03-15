"""Client 模块端口定义。"""

from __future__ import annotations

from .admin_ports import CredentialPort, GsxtReportPort
from .file_upload_port import FileUploadPort
from .file_validator_port import FileValidatorPort
from .task_service_port import TaskServicePort

__all__ = [
    "CredentialPort",
    "FileUploadPort",
    "FileValidatorPort",
    "GsxtReportPort",
    "TaskServicePort",
]
