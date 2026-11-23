"""
财产保全材料生成 API

Requirements: 2.1, 2.2, 3.1, 3.2, 3.3
"""

import logging
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

from .download_response_factory import build_download_response
from .material_common import get_contract_folder_binding_service
from .material_common import require_case_contract as _require_case_contract_shared
from .material_common import save_or_download as _save_or_download_shared

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())

_SAVE_ENDPOINT = "documents.preservation.save_or_download"


def _get_preservation_materials_service() -> Any:
    """工厂函数:获取财产保全材料生成服务"""
    from apps.documents.services.generation.preservation_materials_generation_service import (
        PreservationMaterialsGenerationService,
    )

    return PreservationMaterialsGenerationService()


def _get_folder_binding_service() -> Any:
    """工厂函数:获取合同文件夹绑定服务（测试按模块 monkeypatch 这个点）"""
    return get_contract_folder_binding_service()


# S01-04（2026-11-23 二轮审计）：`_require_case_contract` / `_save_or_download` 的实现已收敛到
# material_common（与授权材料共用同一份 ACL + 落盘口径）。这里保留同名薄封装：端点仍调本模块
# 的名字，测试也按模块 monkeypatch `_get_folder_binding_service`，绑定服务因此仍由本模块解析。
async def _require_case_contract(request: Any, case_id: int) -> Any:
    return await _require_case_contract_shared(request, case_id)


async def _save_or_download(
    request: Any,
    contract_id: int | None,
    case_id: int,
    content: bytes,
    filename: str,
    content_type: str,
    subdir_key: str = "contract_documents",
) -> Any:
    return await _save_or_download_shared(
        request,
        endpoint=_SAVE_ENDPOINT,
        binding_service_getter=_get_folder_binding_service,
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type=content_type,
        subdir_key=subdir_key,
    )


@router.post("/cases/{case_id}/preservation/application/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_preservation_application(request: Any, case_id: int) -> Any:  # pragma: no cover
    """
    下载财产保全申请书

    POST /api/v1/documents/cases/{case_id}/preservation/application/download

    Requirements: 2.1, 3.1
    """
    case = await _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = await sync_to_async(service.generate_preservation_application)(case_id)

    logger.info("财产保全申请书生成成功", extra={"case_id": case_id, "doc_filename": filename})
    return await _save_or_download(
        request,
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/preservation/delay-delivery/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_delay_delivery_application(request: Any, case_id: int) -> Any:  # pragma: no cover
    """
    下载暂缓送达申请书

    POST /api/v1/documents/cases/{case_id}/preservation/delay-delivery/download

    Requirements: 2.2, 3.2
    """
    case = await _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = await sync_to_async(service.generate_delay_delivery_application)(case_id)

    logger.info("暂缓送达申请书生成成功", extra={"case_id": case_id, "doc_filename": filename})
    return await _save_or_download(
        request,
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/preservation/package/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_full_package(request: Any, case_id: int) -> Any:  # pragma: no cover
    """
    下载全套财产保全材料

    POST /api/v1/documents/cases/{case_id}/preservation/package/download

    Requirements: 3.3, 10.1
    """
    from apps.agent.services.approval.write_guard import ensure_request_not_multi_lane

    # 入口 C 兜底：ZIP 不走 `_save_or_download`（改走 extract_zip），单点拦不到
    await ensure_request_not_multi_lane(request, endpoint="documents.preservation.package")

    case = await _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_preservation_materials_service()
    content, filename = await sync_to_async(service.generate_full_package)(case_id)

    logger.info("全套财产保全材料生成成功", extra={"case_id": case_id, "zip_filename": filename})

    # ZIP 包使用 extract_zip 方式保存到合同文件夹根目录
    if contract_id is not None:
        binding_service = _get_folder_binding_service()
        saved_path = await sync_to_async(binding_service.extract_zip_for_contract)(
            contract_id=contract_id, zip_content=content
        )
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
