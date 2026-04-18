"""
文档处理工具API
独立的API模块
"""

from ninja import Router

from apps.automation.schemas import DocumentProcessIn, DocumentProcessOut
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router(tags=["文档处理"])


from typing import Any


def _get_document_processor_service() -> Any:
    from apps.core.dependencies import build_document_processing_service

    return build_document_processing_service()


@router.post("/process", response=DocumentProcessOut)
@rate_limit_from_settings("UPLOAD")
def process_document(request: Any, payload: DocumentProcessIn) -> DocumentProcessOut:
    """文档处理API"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()

    # 调用服务处理文档
    result = service.process_document(
        file_path=payload.file_path, kind=payload.kind, limit=payload.limit, preview_page=payload.preview_page
    )

    return DocumentProcessOut(image_url=result.image_url, text_excerpt=result.text_excerpt)


@router.post("/process-by-path", response=DocumentProcessOut)
@rate_limit_from_settings("UPLOAD")
def process_document_by_path(request: Any, payload: DocumentProcessIn) -> DocumentProcessOut:
    """通过路径处理文档"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()

    # 调用服务处理文档
    result = service.process_document_by_path(
        file_path=payload.file_path, limit=payload.limit, preview_page=payload.preview_page
    )

    return DocumentProcessOut(image_url=result.image_url, text_excerpt=result.text_excerpt)
