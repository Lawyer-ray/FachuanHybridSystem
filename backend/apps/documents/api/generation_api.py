"""
文档生成 API

提供合同文件夹和补充协议的下载接口.
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.auth import JWTOrSessionAuth
from apps.core.exceptions import ValidationException
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _require_contract_access(request: Any, contract_id: int) -> None:
    from apps.core.interfaces import ServiceLocator
    from apps.core.security.access_context import get_request_access_context

    ctx = get_request_access_context(request)
    ServiceLocator.get_contract_query_service().ensure_contract_access_ctx(contract_id=contract_id, ctx=ctx)


def _get_folder_generation_service() -> Any:
    """工厂函数:通过 ServiceLocator 获取 FolderGenerationService 实例"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_folder_generation_service()


def _get_supplementary_agreement_service() -> Any:
    """工厂函数:通过 ServiceLocator 获取 SupplementaryAgreementGenerationService 实例"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_supplementary_agreement_generation_service()


def _get_contract_generation_service() -> Any:
    """工厂函数:通过 ServiceLocator 获取 ContractGenerationService 实例"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_contract_generation_service()


@router.get("/contracts/{contract_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_contract_document(request: Any, contract_id: int) -> Any:
    """
    下载合同文档(DOCX 格式)

    生成单个合同 Word 文档.
    如果合同有文件夹绑定,文件会保存到绑定文件夹,返回 JSON 响应.
    如果没有绑定,返回文件下载响应.

    Args:
        contract_id: 合同 ID

    Returns:
        DOCX 文件下载响应或 JSON 响应
    """
    _require_contract_access(request, contract_id)
    service = _get_contract_generation_service()

    # 生成合同文档
    content, filename, saved_path, error = service.generate_contract_document_result(contract_id)

    if error:
        logger.warning("生成合同文档失败: %s", error, extra={"contract_id": contract_id, "error": error})
        raise ValidationException(
            message="生成合同文档失败", code="CONTRACT_GENERATION_FAILED", errors={"detail": error}
        )

    if saved_path:
        logger.info(
            "合同文档已保存到绑定文件夹",
            extra={
                "contract_id": contract_id,
                "doc_filename": filename,
                "saved_path": saved_path,
            },
        )
        return {
            "success": True,
            "message": f"合同文档已生成并保存到: {saved_path}",
            "filename": filename,
            "folder_path": saved_path,
        }

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info("合同文档下载成功", extra={"contract_id": contract_id, "doc_filename": filename})

    return response


@router.get("/contracts/{contract_id}/folder/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_contract_folder(request: Any, contract_id: int) -> Any:
    """
    下载合同文件夹(ZIP 格式)

    生成包含完整文件夹结构和合同文书的 ZIP 压缩包.

    Args:
        contract_id: 合同 ID

    Returns:
        ZIP 文件下载响应
    """
    _require_contract_access(request, contract_id)
    service = _get_folder_generation_service()

    # 生成文件夹 ZIP
    zip_content, zip_filename, extract_path, error = service.generate_folder_with_documents_result(contract_id)

    if error:
        logger.warning("生成合同文件夹失败: %s", error, extra={"contract_id": contract_id, "error": error})
        raise ValidationException(
            message="生成合同文件夹失败", code="FOLDER_GENERATION_FAILED", errors={"detail": error}
        )

    if extract_path:
        logger.info(
            "合同文件夹已解压到绑定文件夹",
            extra={"contract_id": contract_id, "zip_filename": zip_filename, "extract_path": extract_path},
        )
        return {
            "success": True,
            "message": f"合同文件夹已生成并解压到: {extract_path}",
            "filename": zip_filename,
            "folder_path": extract_path,
        }

    response = build_download_response(content=zip_content, filename=zip_filename, content_type="application/zip")

    logger.info("合同文件夹下载成功", extra={"contract_id": contract_id, "zip_filename": zip_filename})

    return response


@router.get("/contracts/{contract_id}/supplementary-agreements/{agreement_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_supplementary_agreement(request: Any, contract_id: int, agreement_id: int) -> Any:
    """
    下载补充协议文档(DOCX 格式)

    生成补充协议 Word 文档.
    如果合同有文件夹绑定,文件会保存到绑定文件夹,返回 JSON 响应.
    如果没有绑定,返回文件下载响应.

    Args:
        contract_id: 合同 ID
        agreement_id: 补充协议 ID

    Returns:
        DOCX 文件下载响应或 JSON 响应
    """
    _require_contract_access(request, contract_id)
    service = _get_supplementary_agreement_service()

    # 生成补充协议文档
    content, filename, saved_path, error = service.generate_supplementary_agreement_result(contract_id, agreement_id)

    if error:
        logger.warning(
            "生成补充协议失败: %s", error,
            extra={"contract_id": contract_id, "agreement_id": agreement_id, "error": error},
        )
        raise ValidationException(
            message="生成补充协议失败", code="AGREEMENT_GENERATION_FAILED", errors={"detail": error}
        )

    if saved_path:
        logger.info(
            "补充协议已保存到绑定文件夹",
            extra={
                "contract_id": contract_id,
                "agreement_id": agreement_id,
                "doc_filename": filename,
                "saved_path": saved_path,
            },
        )
        return {
            "success": True,
            "message": f"补充协议已生成并保存到: {saved_path}",
            "filename": filename,
            "folder_path": saved_path,
        }

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info(
        "补充协议下载成功", extra={"contract_id": contract_id, "agreement_id": agreement_id, "doc_filename": filename}
    )

    return response
