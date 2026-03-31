"""
授权委托材料生成 API
"""

import logging
from typing import Any

from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_authorization_material_generation_service() -> Any:
    from apps.documents.services.generation.composition import build_authorization_material_generation_service

    return build_authorization_material_generation_service()


def _get_folder_binding_service() -> Any:
    from apps.contracts.services.folder.folder_binding_service import FolderBindingService

    return FolderBindingService()


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
            extra={"case_id": case_id, "contract_id": contract_id, "file_name": filename, "path": saved_path},
        )
        return {"success": True, "message": f"文件已保存到: {saved_path}", "filename": filename, "folder_path": saved_path}

    return build_download_response(content=content, filename=filename, content_type=content_type)


class CombinedPowerOfAttorneyIn(Schema):
    client_ids: list[int]


@router.post("/cases/{case_id}/authorization/letter/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_authority_letter(request: Any, case_id: int) -> Any:
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_authorization_material_generation_service()
    content, filename = service.generate_authority_letter_document(case_id)

    logger.info("所函生成成功", extra={"case_id": case_id, "doc_filename": filename})
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/authorization/legal-rep-certificate/{client_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_legal_rep_certificate(request: Any, case_id: int, client_id: int) -> Any:
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_authorization_material_generation_service()
    content, filename = service.generate_legal_rep_certificate_document(case_id, client_id)

    logger.info(
        "法定代表人身份证明书生成成功",
        extra={"case_id": case_id, "client_id": client_id, "doc_filename": filename},
    )
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/authorization/power-of-attorney/combined/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_power_of_attorney_combined(request: Any, case_id: int, payload: CombinedPowerOfAttorneyIn) -> Any:
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_authorization_material_generation_service()
    content, filename = service.generate_power_of_attorney_combined_document(case_id, payload.client_ids)

    logger.info(
        "授权委托书(合并授权)生成成功",
        extra={"case_id": case_id, "client_ids": payload.client_ids, "doc_filename": filename},
    )
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )


@router.post("/cases/{case_id}/authorization/package/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_authorization_package(request: Any, case_id: int) -> Any:
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_authorization_material_generation_service()
    content, filename = service.generate_full_authorization_package(case_id)

    logger.info("全套授权委托材料生成成功", extra={"case_id": case_id, "zip_filename": filename})

    # ZIP 包使用 extract_zip 方式保存到合同文件夹根目录
    if contract_id is not None:
        binding_service = _get_folder_binding_service()
        saved_path = binding_service.extract_zip_for_contract(contract_id=contract_id, zip_content=content)
        if saved_path:
            logger.info(
                "全套授权委托材料已保存到合同文件夹",
                extra={"case_id": case_id, "contract_id": contract_id, "zip_filename": filename, "path": saved_path},
            )
            return {
                "success": True,
                "message": f"文件已保存到: {saved_path}",
                "filename": filename,
                "folder_path": saved_path,
            }

    return build_download_response(content=content, filename=filename, content_type="application/zip")


@router.post("/cases/{case_id}/authorization/power-of-attorney/{client_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_power_of_attorney(request: Any, case_id: int, client_id: int) -> Any:
    case = _require_case_contract(request, case_id)
    contract_id = case["contract_id"] if case else None

    service = _get_authorization_material_generation_service()
    content, filename = service.generate_power_of_attorney_document(case_id, client_id)

    logger.info(
        "授权委托书生成成功",
        extra={"case_id": case_id, "client_id": client_id, "doc_filename": filename},
    )
    return _save_or_download(
        contract_id=contract_id,
        case_id=case_id,
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        subdir_key="contract_documents",
    )
