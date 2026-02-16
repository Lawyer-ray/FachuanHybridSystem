"""
财产保全材料生成 API

Requirements: 2.1, 2.2, 3.1, 3.2, 3.3
"""

import logging
from typing import Any

from ninja import Router

from apps.core.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_preservation_materials_service() -> Any:
    """工厂函数:获取财产保全材料生成服务"""
    from apps.documents.services.generation.preservation_materials_generation_service import (
        PreservationMaterialsGenerationService,
    )

    return PreservationMaterialsGenerationService()


@router.post("/cases/{case_id}/preservation/application/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_preservation_application(request: Any, case_id: int) -> Any:
    """
    下载财产保全申请书

    POST /api/v1/documents/cases/{case_id}/preservation/application/download

    Requirements: 2.1, 3.1
    """
    service = _get_preservation_materials_service()
    content, filename = service.generate_preservation_application(case_id)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info("财产保全申请书下载成功", extra={"case_id": case_id, "doc_filename": filename})
    return response


@router.post("/cases/{case_id}/preservation/delay-delivery/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_delay_delivery_application(request: Any, case_id: int) -> Any:
    """
    下载暂缓送达申请书

    POST /api/v1/documents/cases/{case_id}/preservation/delay-delivery/download

    Requirements: 2.2, 3.2
    """
    service = _get_preservation_materials_service()
    content, filename = service.generate_delay_delivery_application(case_id)

    response = build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    logger.info("暂缓送达申请书下载成功", extra={"case_id": case_id, "doc_filename": filename})
    return response


@router.post("/cases/{case_id}/preservation/package/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_full_package(request: Any, case_id: int) -> Any:
    """
    下载全套财产保全材料

    POST /api/v1/documents/cases/{case_id}/preservation/package/download

    Requirements: 3.3, 10.1
    """
    service = _get_preservation_materials_service()
    content, filename = service.generate_full_package(case_id)

    response = build_download_response(content=content, filename=filename, content_type="application/zip")

    logger.info("全套财产保全材料下载成功", extra={"case_id": case_id, "zip_filename": filename})
    return response
