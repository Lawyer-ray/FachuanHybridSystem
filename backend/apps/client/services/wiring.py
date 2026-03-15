"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

from apps.client.adapters import (
    CredentialAdapter,
    FileUploadAdapter,
    FileValidatorAdapter,
    GsxtReportAdapter,
    TaskServiceAdapter,
)
from apps.client.ports import (
    CredentialPort,
    FileUploadPort,
    FileValidatorPort,
    GsxtReportPort,
    TaskServicePort,
)

if TYPE_CHECKING:
    from apps.core.protocols import ILLMService


def get_llm_service() -> ILLMService:
    return ServiceLocator.get_llm_service()


# ==================== Port Factories ====================


def get_gsxt_report_port() -> GsxtReportPort:
    """获取企业信用报告端口。"""
    return GsxtReportAdapter()


def get_credential_port() -> CredentialPort:
    """获取账号凭证端口。"""
    return CredentialAdapter()


def get_file_upload_port() -> FileUploadPort:
    """获取文件上传端口。"""
    return FileUploadAdapter()


def get_file_validator_port() -> FileValidatorPort:
    """获取文件验证端口。"""
    return FileValidatorAdapter()


def get_task_service_port() -> TaskServicePort:
    """获取任务服务端口。"""
    return TaskServiceAdapter()
