"""
自动命名服务适配器

提供自动命名服务的统一接口实现
"""
import logging
from typing import Optional, Dict, Any
from django.conf import settings

from apps.core.interfaces import IAutoNamerService, IDocumentProcessingService, ServiceLocator
from apps.automation.services.ai.ollama_client import chat as ollama_chat
from apps.automation.services.ai.prompts import DEFAULT_FILENAME_PROMPT

logger = logging.getLogger("apps.automation")


class AutoNamerServiceAdapter(IAutoNamerService):
    """
    自动命名服务适配器
    
    实现 IAutoNamerService 接口，提供基于AI的自动命名功能
    """
    
    def __init__(
        self,
        document_service: Optional[IDocumentProcessingService] = None
    ):
        """
        初始化服务适配器
        
        Args:
            document_service: 文档处理服务（可选）
        """
        self._document_service = document_service
    
    @property
    def document_service(self) -> IDocumentProcessingService:
        """获取文档处理服务（延迟加载）"""
        if self._document_service is None:
            self._document_service = ServiceLocator.get_document_processing_service()
        return self._document_service
    
    def generate_filename(
        self,
        document_content: str,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b"
    ) -> str:
        """
        根据文档内容生成文件名
        
        Args:
            document_content: 文档文本内容
            prompt: 自定义提示词（可选）
            model: 使用的AI模型
            
        Returns:
            生成的文件名建议
        """
        try:
            # 验证输入
            if not document_content or not document_content.strip():
                from apps.core.exceptions import AutomationExceptions
                raise AutomationExceptions.empty_document_content()
            
            # 使用默认提示词
            if prompt is None:
                prompt = DEFAULT_FILENAME_PROMPT
            
            logger.info(
                "开始生成文件名",
                extra={
                    "action": "generate_filename_start",
                    "content_length": len(document_content),
                    "model": model,
                    "has_custom_prompt": prompt != DEFAULT_FILENAME_PROMPT
                }
            )
            
            # 调用AI服务生成文件名
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": document_content}
            ]
            
            base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_result = ollama_chat(model=model, messages=messages, base_url=base_url)
            
            # 提取生成的文件名
            if ollama_result and "message" in ollama_result and "content" in ollama_result["message"]:
                filename = ollama_result["message"]["content"].strip()
                
                logger.info(
                    "文件名生成成功",
                    extra={
                        "action": "generate_filename_success",
                        "generated_filename": filename,
                        "model": model
                    }
                )
                
                return filename
            else:
                raise Exception("AI服务返回格式异常")
                
        except Exception as e:
            logger.error(
                f"文件名生成失败: {e}",
                extra={
                    "action": "generate_filename_failed",
                    "content_length": len(document_content) if document_content else 0,
                    "model": model,
                    "error": str(e)
                },
                exc_info=True
            )
            
            if isinstance(e, ValidationException):
                raise
            else:
                from apps.core.exceptions import AutomationExceptions
                raise AutomationExceptions.ai_filename_generation_failed(str(e))
    
    def process_document_for_naming(
        self,
        uploaded_file: Any,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b",
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理文档并生成命名建议
        
        Args:
            uploaded_file: 上传的文件对象
            prompt: 自定义提示词（可选）
            model: 使用的AI模型
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本内容、命名建议等信息的字典
        """
        try:
            logger.info(
                "开始处理文档并生成命名",
                extra={
                    "action": "process_document_for_naming_start",
                    "filename": uploaded_file.name if hasattr(uploaded_file, 'name') else None,
                    "model": model
                }
            )
            
            # 处理文档提取文本
            document_result = self.document_service.process_uploaded_document(
                uploaded_file, limit=limit, preview_page=preview_page
            )
            
            text_content = document_result.get("text", "").strip()
            
            if not text_content:
                error_msg = "文档中没有提取到文字内容，无法生成命名。"
                if document_result.get("image_url"):
                    error_msg += f"已生成的预览图：{document_result['image_url']}"
                
                return {
                    "text": None,
                    "filename_suggestion": None,
                    "error": error_msg,
                    "image_url": document_result.get("image_url"),
                    "original_filename": uploaded_file.name if hasattr(uploaded_file, 'name') else None
                }
            
            # 生成文件名建议
            try:
                filename_suggestion = self.generate_filename(text_content, prompt, model)
                
                logger.info(
                    "文档处理和命名生成完成",
                    extra={
                        "action": "process_document_for_naming_success",
                        "text_length": len(text_content),
                        "filename_suggestion": filename_suggestion
                    }
                )
                
                return {
                    "text": text_content,
                    "filename_suggestion": filename_suggestion,
                    "error": None,
                    "image_url": document_result.get("image_url"),
                    "original_filename": uploaded_file.name if hasattr(uploaded_file, 'name') else None,
                    "model_used": model
                }
                
            except Exception as ai_error:
                logger.warning(
                    f"AI命名生成失败，但文档处理成功: {ai_error}",
                    extra={
                        "action": "process_document_for_naming_partial_success",
                        "text_length": len(text_content),
                        "ai_error": str(ai_error)
                    }
                )
                
                return {
                    "text": text_content,
                    "filename_suggestion": None,
                    "error": f"AI命名生成失败: {str(ai_error)}",
                    "image_url": document_result.get("image_url"),
                    "original_filename": uploaded_file.name if hasattr(uploaded_file, 'name') else None
                }
                
        except Exception as e:
            logger.error(
                f"文档处理和命名生成失败: {e}",
                extra={
                    "action": "process_document_for_naming_failed",
                    "filename": uploaded_file.name if hasattr(uploaded_file, 'name') else None,
                    "error": str(e)
                },
                exc_info=True
            )
            
            if isinstance(e, (ValidationException, BusinessException)):
                raise
            else:
                from apps.core.exceptions import AutomationExceptions
                raise AutomationExceptions.document_naming_processing_failed(str(e))
    
    # 内部方法版本，供其他模块调用
    def generate_filename_internal(
        self,
        document_content: str,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b"
    ) -> str:
        """根据文档内容生成文件名（内部接口，无权限检查）"""
        return self.generate_filename(document_content, prompt, model)
    
    def process_document_for_naming_internal(
        self,
        uploaded_file: Any,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b",
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """处理文档并生成命名建议（内部接口，无权限检查）"""
        return self.process_document_for_naming(uploaded_file, prompt, model, limit, preview_page)