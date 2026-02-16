"""
授权委托材料生成 API
"""

import logging
from typing import Any

from ninja import Router, Schema

from apps.core.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_authorization_material_generation_service() -> Any:
    from apps.documents.services.generation.composition import build_authorization_material_generation_service

    return build_authorization_material_generation_service()


class CombinedPowerOfAttorneyIn(Schema):
    client_ids: list[int]


@router.post("/cases/{case_id}/authorization/letter/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_authority_letter(request: Any, case_id: int) -> Any:
    service = _get_authorization_material_generation_service()
    content, filename = service.generate_authority_letter_document(case_id)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info("所函下载成功", extra={"case_id": case_id, "doc_filename": filename})
    return response


@router.post("/cases/{case_id}/authorization/legal-rep-certificate/{client_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_legal_rep_certificate(request: Any, case_id: int, client_id: int) -> Any:
    service = _get_authorization_material_generation_service()
    content, filename = service.generate_legal_rep_certificate_document(case_id, client_id)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info(
        "法定代表人身份证明书下载成功",
        extra={"case_id": case_id, "client_id": client_id, "doc_filename": filename},
    )
    return response


@router.post("/cases/{case_id}/authorization/power-of-attorney/combined/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_power_of_attorney_combined(request: Any, case_id: int, payload: CombinedPowerOfAttorneyIn) -> Any:
    service = _get_authorization_material_generation_service()
    content, filename = service.generate_power_of_attorney_combined_document(case_id, payload.client_ids)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info(
        "授权委托书(合并授权)下载成功",
        extra={"case_id": case_id, "client_ids": payload.client_ids, "doc_filename": filename},
    )
    return response


@router.post("/cases/{case_id}/authorization/package/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_authorization_package(request: Any, case_id: int) -> Any:
    service = _get_authorization_material_generation_service()
    content, filename = service.generate_full_authorization_package(case_id)

    response = build_download_response(content=content, filename=filename, content_type="application/zip")

    logger.info("全套授权委托材料下载成功", extra={"case_id": case_id, "zip_filename": filename})
    return response


@router.post("/cases/{case_id}/authorization/power-of-attorney/{client_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_power_of_attorney(request: Any, case_id: int, client_id: int) -> Any:
    service = _get_authorization_material_generation_service()
    content, filename = service.generate_power_of_attorney_document(case_id, client_id)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info(
        "授权委托书下载成功",
        extra={"case_id": case_id, "client_id": client_id, "doc_filename": filename},
    )
    return response
