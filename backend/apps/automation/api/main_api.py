"""
主要API模块
集成所有工具的API接口
"""
from ninja import Router, File
from ninja.files import UploadedFile
from django.conf import settings

from ..schemas import (
    OllamaChatIn, OllamaChatOut, 
    MoonshotChatIn, MoonshotChatOut
)
from .performance_monitor_api import router as performance_router

router = Router(tags=["Main API"])


def _get_ai_service():
    """
    工厂函数：创建AI服务实例
    
    通过ServiceLocator获取AI服务，确保依赖解耦
    
    Returns:
        IAIService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_ai_service()


def _get_document_processor_service():
    """
    工厂函数：创建文档处理服务实例
    
    通过ServiceLocator获取文档处理服务，确保依赖解耦
    
    Returns:
        IDocumentProcessorService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_document_processor_service()


def _get_config_service():
    """
    工厂函数：创建配置服务实例
    
    通过ServiceLocator获取配置服务，确保依赖解耦
    
    Returns:
        IConfigService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_config_service()

# 添加性能监控子路由
router.add_router("/performance", performance_router)

# ============================================================================
# AI集成API
# ============================================================================

@router.post("/ai/ollama", response=OllamaChatOut)
def ai_ollama(request, payload: OllamaChatIn):
    """Ollama AI接口"""
    # 使用工厂函数获取服务
    service = _get_ai_service()
    
    # 调用服务处理Ollama聊天
    result = service.chat_with_ollama(
        model=payload.model,
        prompt=payload.prompt,
        text=payload.text
    )
    
    return OllamaChatOut(data=result)


@router.post("/ai/moonshot", response=MoonshotChatOut)
def ai_moonshot(request, payload: MoonshotChatIn):
    """Moonshot AI接口"""
    # 使用工厂函数获取服务
    service = _get_ai_service()
    
    # 调用服务处理Moonshot聊天
    result = service.chat_with_moonshot(
        model=payload.model,
        prompt=payload.prompt,
        text=payload.text
    )
    
    return MoonshotChatOut(data=result)


# ============================================================================
# 通用工具API
# ============================================================================

@router.post("/file/upload", response=dict)
def upload_file(
    request,
    file: UploadedFile = File(...),
    limit: int | None = None,
    preview_page: int | None = None
):
    """通用文件上传和预处理API"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()
    
    # 调用服务处理文件上传
    result = service.process_uploaded_file(
        uploaded_file=file,
        limit=limit,
        preview_page=preview_page
    )
    
    return {
        "success": result.success,
        "file_info": result.file_info,
        "extraction": result.extraction,
        "processing_params": result.processing_params,
        "error": result.error
    }


# ============================================================================
# 配置和状态API
# ============================================================================

@router.get("/config")
def get_config(request):
    """获取当前配置信息"""
    # 使用工厂函数获取服务
    service = _get_config_service()
    
    # 调用服务获取配置信息
    config = service.get_automation_config()
    
    return config


@router.get("/status")
def get_status(request):
    """获取系统状态"""
    # 使用工厂函数获取服务
    service = _get_config_service()
    
    # 调用服务获取系统状态
    status = service.get_system_status()
    
    return status
