import logging
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from ninja import File, Router, Schema
from ninja.files import UploadedFile

from apps.client.schemas import IdentityDocDetailOut, IdentityRecognizeOut
from apps.client.services.storage import save_uploaded_file
from apps.core.services.django_q_tasks import get_q_task_status, submit_q_task

logger = logging.getLogger(__name__)

router = Router()


def _get_identity_doc_service() -> Any:
    """工厂函数：创建 ClientIdentityDocService 实例"""
    from apps.client.services import ClientIdentityDocService

    return ClientIdentityDocService()


def _get_client_service() -> Any:
    """工厂函数：创建 ClientService 实例"""
    from apps.client.services import ClientService

    return ClientService()


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
    file: UploadedFile = File(...),  # type: ignore[arg-type]
    doc_type: str = "身份证",
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
    file: UploadedFile = File(...),  # type: ignore[arg-type]
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
        media_url=identity_doc.media_url(),
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


@router.get("/parse-text")
def parse_text(request: Any, text: str = "") -> dict[str, Any]:
    """
    解析客户文本

    Args:
        request: HTTP 请求
        text: 待解析的文本（查询参数）

    Returns:
        解析后的客户数据
    """
    service = _get_client_service()
    parsed_data = service.parse_client_text(text)

    return cast(dict[str, Any], parsed_data)


class MergeIdCardManualIn(Schema):
    """手动合并身份证请求体"""

    front_image_path: str
    back_image_path: str
    front_corners: list[list[int]]
    back_corners: list[list[int]]


@router.post("/identity-docs/merge-id-card")
def merge_id_card(
    request: Any,
    front_image: UploadedFile = File(...),  # type: ignore[arg-type]
    back_image: UploadedFile = File(...),  # type: ignore[arg-type]
) -> dict[str, Any]:
    """自动检测并合并身份证正反面为 PDF"""
    service = _get_id_card_merge_service()
    result: dict[str, Any] = service.merge_id_card_with_detection(front_image, back_image)
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


@router.post("/identity-doc/recognize/submit")
def submit_recognize_task(
    request: Any,
    file: UploadedFile = File(...),  # type: ignore[arg-type]
) -> dict[str, Any]:
    """提交证件识别异步任务"""
    rel_path, _ = save_uploaded_file(file, rel_dir="client_docs/recognize")
    task_id: str = submit_q_task(
        "apps.client.services.identity_extraction.extraction_service.extract_identity_doc_task",
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
    result: dict[str, Any] = get_q_task_status(task_id)
    return result
