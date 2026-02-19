"""
文档处理工具API
独立的API模块
"""

from ninja import Router

from apps.automation.schemas import DocumentProcessIn, DocumentProcessOut
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router(tags=["Document Processor"])


from typing import Any


def _get_document_processor_service() -> Any:
    """
    工厂函数：创建文档处理服务实例

    通过ServiceLocator获取文档处理服务，确保依赖解耦

    Returns:
        IDocumentProcessorService 实例
    """
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_document_processor_service()  # type: ignore[attr-defined]


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
