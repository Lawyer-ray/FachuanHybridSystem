import logging
from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import File, Router, Schema
from ninja.files import UploadedFile

from apps.client.schemas import IdentityDocDetailOut, IdentityRecognizeOut
from apps.client.services.wiring import get_task_service_port
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger(__name__)

router = Router()


def _get_identity_doc_service() -> Any:
    """工厂函数：创建 ClientIdentityDocService 实例"""
    from apps.client.services import ClientIdentityDocService

    return ClientIdentityDocService()


def _get_identity_extraction_service() -> Any:
    """工厂函数：创建 IdentityExtractionService 实例"""
    from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService

    return IdentityExtractionService()


def _get_id_card_merge_service() -> Any:
    """工厂函数：创建 IdCardMergeService 实例"""
    from apps.client.services.id_card_merge import IdCardMergeService

    return IdCardMergeService()


@router.post("/identity-doc/recognize", response=IdentityRecognizeOut)
def recognize_identity_doc(
    request: Any,
    file: UploadedFile = File(...),
    doc_type: str = "id_card",
) -> IdentityRecognizeOut:
    """识别证件信息"""
    image_bytes = file.read()
    service = _get_identity_extraction_service()
    result = service.safe_extract(image_bytes, doc_type)
    return IdentityRecognizeOut(
        success=result["success"],
        doc_type=result["doc_type"],
        extracted_data=result["extracted_data"],
        confidence=result["confidence"],
        error=result.get("error"),
    )


@router.post("/clients/{client_id}/identity-docs")
def add_identity_doc(
    request: Any,
    client_id: int,
    doc_type: str,
    file: UploadedFile = File(...),
) -> dict[str, Any]:
    """添加证件文档"""
    service = _get_identity_doc_service()
    identity_doc = service.add_identity_doc_from_upload(
        client_id=client_id,
        doc_type=doc_type,
        uploaded_file=file,
        user=getattr(request, "user", None),
    )
    return {"success": True, "doc_id": identity_doc.id, "message": _("证件文档添加成功")}


class MergeIdCardManualIn(Schema):
    """手动合并身份证请求体"""

    front_image_path: str
    back_image_path: str
    front_corners: list[list[int]]
    back_corners: list[list[int]]


@router.post("/identity-docs/merge-id-card")
def merge_id_card(
    request: Any,
    front_image: UploadedFile = File(...),
    back_image: UploadedFile = File(...),
    client_id: int | None = None,
) -> dict[str, Any]:
    """自动检测并合并身份证正反面为 PDF，可选保存到客户证件"""
    service = _get_id_card_merge_service()
    result: dict[str, Any] = service.merge_id_card_with_detection(front_image, back_image)
    if result.get("success") and client_id:
        doc_service = _get_identity_doc_service()
        doc = doc_service.add_identity_doc(
            client_id=client_id,
            doc_type="id_card",
            file_path=result["pdf_path"],
        )
        result["doc_id"] = doc.id
    return result


@router.post("/identity-docs/merge-id-card-direct")
def merge_id_card_direct(
    request: Any,
    front_image: UploadedFile = File(...),
    back_image: UploadedFile = File(...),
    client_id: int | None = None,
) -> dict[str, Any]:
    """直接合并已裁剪的身份证正反面为 PDF（前端已完成裁剪），可选保存到客户证件"""
    service = _get_id_card_merge_service()
    result: dict[str, Any] = service.merge_id_card(front_image, back_image)
    if result.get("success") and client_id:
        doc_service = _get_identity_doc_service()
        doc = doc_service.add_identity_doc(
            client_id=client_id,
            doc_type="id_card",
            file_path=result["pdf_path"],
        )
        result["doc_id"] = doc.id
    return result


@router.post("/identity-docs/merge-id-card-manual")
def merge_id_card_manual(
    request: Any,
    data: MergeIdCardManualIn,
) -> dict[str, Any]:
    """手动指定四角坐标合并身份证"""
    service = _get_id_card_merge_service()
    result: dict[str, Any] = service.merge_id_card_manual(
        front_image_path=data.front_image_path,
        back_image_path=data.back_image_path,
        front_corners=data.front_corners,
        back_corners=data.back_corners,
    )
    return result


@router.get("/identity-docs/{doc_id}", response=IdentityDocDetailOut)
def get_identity_doc(request: Any, doc_id: int) -> IdentityDocDetailOut:
    """
    获取证件文档

    Args:
        request: HTTP 请求
        doc_id: 证件文档 ID

    Returns:
        证件文档信息
    """
    service = _get_identity_doc_service()
    identity_doc = service.get_identity_doc(doc_id)

    return IdentityDocDetailOut(
        id=identity_doc.id,
        client_id=identity_doc.client_id,
        doc_type=identity_doc.doc_type,
        file_path=identity_doc.file_path,
        uploaded_at=identity_doc.uploaded_at,
        media_url=identity_doc.media_url,
    )


@router.delete("/identity-docs/{doc_id}")
def delete_identity_doc(request: Any, doc_id: int) -> dict[str, Any]:
    """
    删除证件文档

    Args:
        request: HTTP 请求
        doc_id: 证件文档 ID

    Returns:
        操作结果
    """
    service = _get_identity_doc_service()
    service.delete_identity_doc(doc_id=doc_id, user=getattr(request, "user", None))

    return {"success": True, "message": _("证件文档删除成功")}


@router.post("/identity-doc/recognize/submit")
@rate_limit_from_settings("TASK", by_user=True)
def submit_recognize_task(
    request: Any,
    file: UploadedFile = File(...),
) -> dict[str, Any]:
    """提交证件识别异步任务"""
    service = _get_identity_doc_service()
    rel_path = service.save_uploaded_file_to_dir(file, rel_dir="client_docs/recognize")
    task_service = get_task_service_port()
    task_id: str = task_service.submit_task(
        "apps.client.tasks.execute_identity_doc_recognition",
        rel_path,
    )
    logger.info("证件识别任务已提交", extra={"task_id": task_id, "file_path": rel_path})
    return {"task_id": task_id, "status": "pending"}


@router.get("/identity-doc/task/{task_id}")
def get_recognize_task_status(
    request: Any,
    task_id: str,
) -> dict[str, Any]:
    """查询证件识别任务状态"""
    task_service = get_task_service_port()
    result: dict[str, Any] = task_service.get_task_status(task_id)
    return result
