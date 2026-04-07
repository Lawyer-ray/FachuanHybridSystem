"""
财产保全材料生成 API

Requirements: 2.1, 2.2, 3.1, 3.2, 3.3
"""

import logging
from typing import Any

from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_preservation_materials_service() -> Any:
    """工厂函数:获取财产保全材料生成服务"""
    from apps.documents.services.generation.preservation_materials_generation_service import (
        PreservationMaterialsGenerationService,
    )

    return PreservationMaterialsGenerationService()


def _get_folder_binding_service() -> Any:
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_contract_folder_binding_service()


def _require_case_contract(request: Any, case_id: int) -> Any:
    """获取案件绑定的合同 ID，无合同则返回 None。"""
    from apps.cases.models import Case

    case = Case.objects.filter(pk=case_id).values("contract_id", "contract__folder_binding__id").first()
    if not case:
        return None
    return case


def _save_or_download(
    contract_id: int | None,
    case_id: int,
    content: bytes,
    filename: str,
    content_type: str,
    subdir_key: str = "contract_documents",
) -> Any:
    """如有合同文件夹绑定则保存文件，否则返回下载响应。"""
    if contract_id is None:
        return build_download_response(content=content, filename=filename, content_type=content_type)

    binding_service = _get_folder_binding_service()
    saved_path = binding_service.save_file_for_contract(
        contract_id=contract_id,
        file_content=content,
        file_name=filename,
        subdir_key=subdir_key,
    )
    if saved_path:
        logger.info(
            "文件已保存到合同文件夹",
            extra={"case_id": case_id, "contract_id": contract_id, "filename": filename, "path": saved_path},
        )
        return {
            "success": True,
            "message": f"文件已保存到: {saved_path}",
            "filename": filename,
            "folder_path": saved_path,
        }

    return build_download_response(content=content, filename=filename, content_type=content_type)


@router.post("/cases/{case_id}/preservation/application/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_preservation_application(request: Any, case_id: int) -> Any:
    """
    下载财产保全申请书

    POST /api/v1/documents/cases/{case_id}/preservation/application/download

    Requirements: 2.1, 3.1
    """
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = service.generate_preservation_application(case_id)

    logger.info("财产保全申请书生成成功", extra={"case_id": case_id, "doc_filename": filename})
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/preservation/delay-delivery/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_delay_delivery_application(request: Any, case_id: int) -> Any:
    """
    下载暂缓送达申请书

    POST /api/v1/documents/cases/{case_id}/preservation/delay-delivery/download

    Requirements: 2.2, 3.2
    """
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = service.generate_delay_delivery_application(case_id)

    logger.info("暂缓送达申请书生成成功", extra={"case_id": case_id, "doc_filename": filename})
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/preservation/package/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_full_package(request: Any, case_id: int) -> Any:
    """
    下载全套财产保全材料

    POST /api/v1/documents/cases/{case_id}/preservation/package/download

    Requirements: 3.3, 10.1
    """
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = service.generate_full_package(case_id)

    logger.info("全套财产保全材料生成成功", extra={"case_id": case_id, "zip_filename": filename})

    # ZIP 包使用 extract_zip 方式保存到合同文件夹根目录
    if contract_id is not None:
        binding_service = _get_folder_binding_service()
        saved_path = binding_service.extract_zip_for_contract(contract_id=contract_id, zip_content=content)
        if saved_path:
            logger.info(
                "全套财产保全材料已保存到合同文件夹",
                extra={"case_id": case_id, "contract_id": contract_id, "zip_filename": filename, "path": saved_path},
            )
            return {
                "success": True,
                "message": f"文件已保存到: {saved_path}",
                "filename": filename,
                "folder_path": saved_path,
            }

    return build_download_response(content=content, filename=filename, content_type="application/zip")
