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
