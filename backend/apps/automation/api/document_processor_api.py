"""
文档处理工具API
独立的API模块
"""
from ninja import Router

from ..schemas import DocumentProcessIn, DocumentProcessOut

router = Router(tags=["Document Processor"])


def _get_document_processor_service():
    """
    工厂函数：创建文档处理服务实例
    
    通过ServiceLocator获取文档处理服务，确保依赖解耦
    
    Returns:
        IDocumentProcessorService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_document_processor_service()


@router.post("/process", response=DocumentProcessOut)
def process_document(request, payload: DocumentProcessIn):
    """文档处理API"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()
    
    # 调用服务处理文档
    result = service.process_document(
        file_path=payload.file_path,
        kind=payload.kind,
        limit=payload.limit,
        preview_page=payload.preview_page
    )
    
    return DocumentProcessOut(
        image_url=result.image_url,
        text_excerpt=result.text_excerpt
    )


@router.post("/process-by-path", response=DocumentProcessOut)
def process_document_by_path(request, payload: DocumentProcessIn):
    """通过路径处理文档"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()
    
    # 调用服务处理文档
    result = service.process_document_by_path(
        file_path=payload.file_path,
        limit=payload.limit,
        preview_page=payload.preview_page
    )
    
    return DocumentProcessOut(
        image_url=result.image_url,
        text_excerpt=result.text_excerpt
    )
