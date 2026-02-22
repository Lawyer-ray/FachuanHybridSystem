"""Module for tasks."""

from typing import Any

from apps.client.services.identity_extraction import IdentityExtractionService
from apps.client.services.storage import delete_media_file, to_media_abs


def execute_identity_doc_recognition(file_path: str, doc_type: str) -> dict[str, Any]:
    abs_path = to_media_abs(file_path)
    try:
        content = abs_path.read_bytes()
        service = IdentityExtractionService()
        result = service.extract(content, doc_type)
        return {
            "doc_type": result.doc_type,
            "extracted_data": result.extracted_data,
            "confidence": result.confidence,
        }
    finally:
        delete_media_file(file_path)


def recognize_expiry_date_task(doc_id: int) -> dict[str, Any]:
    """识别证件到期日期并更新数据库。"""
    from datetime import date

    from apps.client.services.client_identity_doc_service import ClientIdentityDocService
    from apps.client.services.identity_extraction.extraction_service import IdentityExtractionService as _Service

    doc_service = ClientIdentityDocService()
    doc = doc_service.get_identity_doc(doc_id)
    abs_path = to_media_abs(doc.file_path)
    content = abs_path.read_bytes()
    service = _Service()
    result = service.extract(content, doc.doc_type)
    expiry_str: str | None = result.extracted_data.get("expiry_date")
    if expiry_str:
        expiry_date = date.fromisoformat(expiry_str)
        doc_service.update_expiry_date(doc_id, expiry_date)
    return {"status": "success", "doc_id": doc_id, "expiry_date": expiry_str}
