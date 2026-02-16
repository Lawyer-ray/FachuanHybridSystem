"""
文档处理服务适配器

提供文档处理服务的统一接口实现
"""
from typing import Optional, Dict, Any
from apps.core.interfaces import IDocumentProcessingService
from apps.automation.services.document.document_processing import (
    process_pdf,
    extract_docx_text,
    extract_text_from_image_with_rapidocr,
    process_uploaded_document,
    extract_document_content
)


class DocumentProcessingServiceAdapter(IDocumentProcessingService):
    """
    文档处理服务适配器
    
    实现 IDocumentProcessingService 接口，提供文档处理的核心功能
    """
    
    def __init__(self):
        """
        初始化文档处理服务适配器
        
        支持依赖注入模式，所有依赖通过延迟加载获取
        """
        pass
    
    def extract_text_from_pdf(
        self,
        file_path: str,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从PDF文件提取文本
        
        Args:
            file_path: PDF文件路径
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本和预览图的字典
        """
        try:
            image_url, text = process_pdf(file_path, limit, preview_page)
            return {
                "text": text,
                "image_url": image_url,
                "file_path": file_path,
                "file_type": "pdf"
            }
        except Exception as e:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.pdf_processing_failed(str(e))
    
    def extract_text_from_docx(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """
        从DOCX文件提取文本
        
        Args:
            file_path: DOCX文件路径
            limit: 文本长度限制
            
        Returns:
            提取的文本内容
        """
        try:
            return extract_docx_text(file_path, limit=limit)
        except Exception as e:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.docx_processing_failed(str(e))
    
    def extract_text_from_image(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """
        从图片文件提取文本（OCR）
        
        Args:
            file_path: 图片文件路径
            limit: 文本长度限制
            
        Returns:
            OCR识别的文本内容
        """
        try:
            text = extract_text_from_image_with_rapidocr(file_path)
            
            if limit is not None and len(text) > limit:
                text = text[:limit]
                
            return text
        except Exception as e:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.image_ocr_failed(str(e))
    
    def process_uploaded_document(
        self,
        uploaded_file: Any,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理上传的文档
        
        Args:
            uploaded_file: 上传的文件对象
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本和预览信息的字典
        """
        try:
            result = process_uploaded_document(uploaded_file, limit=limit, preview_page=preview_page)
            return {
                "text": result.text,
                "image_url": result.image_url,
                "file_name": uploaded_file.name if hasattr(uploaded_file, 'name') else None,
                "file_size": uploaded_file.size if hasattr(uploaded_file, 'size') else None
            }
        except Exception as e:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.document_content_extraction_failed(str(e))
    
    def extract_document_content_by_path(
        self,
        file_path: str,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        根据文件路径提取文档内容
        
        Args:
            file_path: 文件路径
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本和预览信息的字典
        """
        try:
            result = extract_document_content(file_path, limit=limit, preview_page=preview_page)
            return {
                "text": result.text,
                "image_url": result.image_url,
                "file_path": file_path
            }
        except Exception as e:
            from apps.core.exceptions import ValidationException
            raise ValidationException(
                message=f"文档内容提取失败: {str(e)}",
                code="DOCUMENT_CONTENT_EXTRACTION_FAILED",
                errors={"file_path": file_path, "error": str(e)}
            )
    
    # 内部方法版本，供其他模块调用
    def extract_text_from_pdf_internal(
        self,
        file_path: str,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """从PDF文件提取文本（内部接口，无权限检查）"""
        return self.extract_text_from_pdf(file_path, limit, preview_page)
    
    def extract_text_from_docx_internal(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """从DOCX文件提取文本（内部接口，无权限检查）"""
        return self.extract_text_from_docx(file_path, limit)
    
    def extract_text_from_image_internal(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """从图片文件提取文本（内部接口，无权限检查）"""
        return self.extract_text_from_image(file_path, limit)
    
    def process_uploaded_document_internal(
        self,
        uploaded_file: Any,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """处理上传的文档（内部接口，无权限检查）"""
        return self.process_uploaded_document(uploaded_file, limit, preview_page)
    
    def extract_document_content_by_path_internal(
        self,
        file_path: str,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """根据文件路径提取文档内容（内部接口，无权限检查）"""
        return self.extract_document_content_by_path(file_path, limit, preview_page)