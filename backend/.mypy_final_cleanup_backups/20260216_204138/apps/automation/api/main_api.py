"""
主要API模块
集成所有工具的API接口
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from ninja import File, Router
from ninja.files import UploadedFile

from ..schemas import MoonshotChatIn, MoonshotChatOut, OllamaChatIn, OllamaChatOut
from .performance_monitor_api import router as performance_router

router = Router(tags=["Main API"])


def _get_ai_service() -> Any:
    """
    工厂函数：创建AI服务实例

    通过ServiceLocator获取AI服务，确保依赖解耦

    Returns:
        IAIService 实例
    """
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_ai_service()


def _get_document_processor_service() -> Any:
    """
    工厂函数：创建文档处理服务实例

    通过ServiceLocator获取文档处理服务，确保依赖解耦

    Returns:
        IDocumentProcessorService 实例
    """
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_document_processor_service()  # type: ignore[ServiceLocator]


def _get_config_service() -> Any:
    """
    工厂函数：创建配置服务实例

    通过ServiceLocator获取配置服务，确保依赖解耦

    Returns:
        IConfigService 实例
    """
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_config_service()


router.add_router("/performance", performance_router)


@router.post("/ai/ollama", response=OllamaChatOut)
def ai_ollama(request: Any, payload: OllamaChatIn) -> Any:
    """Ollama AI接口"""
    service = _get_ai_service()
    result = service.chat_with_ollama(model=payload.model, prompt=payload.prompt, text=payload.text)
    return OllamaChatOut(data=result)


@router.post("/ai/moonshot", response=MoonshotChatOut)
def ai_moonshot(request: Any, payload: MoonshotChatIn) -> Any:
    """Moonshot AI接口"""
    service = _get_ai_service()
    result = service.chat_with_moonshot(model=payload.model, prompt=payload.prompt, text=payload.text)
    return MoonshotChatOut(data=result)


@router.post("/file/upload", response=dict)
def upload_file(
    request: Any, file: UploadedFile = File(...), limit: int | None = None, preview_page: int | None = None
) -> dict[str, Any]:
    """通用文件上传和预处理API"""
    service = _get_document_processor_service()
    result = service.process_uploaded_file(uploaded_file=file, limit=limit, preview_page=preview_page)
    return {
        "success": result.success,
        "file_info": result.file_info,
        "extraction": result.extraction,
        "processing_params": result.processing_params,
        "error": result.error,
    }


@router.get("/config")
def get_config(request: Any) -> Any:
    """获取当前配置信息"""
    service = _get_config_service()
    config = service.get_automation_config()
    return config


@router.get("/status")
def get_status(request: Any) -> Any:
    """获取系统状态"""
    service = _get_config_service()
    status = service.get_system_status()
    return status
