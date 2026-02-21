import logging
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from ninja import File, Router
from ninja.files import UploadedFile

from apps.client.schemas import IdentityRecognizeOut

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


@router.get("/identity-docs/{doc_id}")
def get_identity_doc(request: Any, doc_id: int) -> dict[str, Any]:
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

    return {
        "id": identity_doc.id,
        "client_id": identity_doc.client_id,
        "doc_type": identity_doc.doc_type,
        "file_path": identity_doc.file_path,
        "created_at": identity_doc.created_at.isoformat() if hasattr(identity_doc, "created_at") else None,
        "updated_at": identity_doc.updated_at.isoformat() if hasattr(identity_doc, "updated_at") else None,
    }


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


@router.api_operation(["GET", "POST"], "/parse-text")
def parse_text_any(request: Any) -> dict[str, Any]:
    """
    解析客户文本

    Args:
        request: HTTP 请求

    Returns:
        解析后的客户数据
    """
    text = request.GET.get("text") or request.POST.get("text") or ""

    # 委托给 ClientService 处理文本解析
    service = _get_client_service()
    parsed_data = service.parse_client_text(text)

    return cast(dict[str, Any], parsed_data)
