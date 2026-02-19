"""
主要API模块
集成所有工具的API接口
"""

from typing import Any

from ninja import File, Router
from ninja.files import UploadedFile

from apps.automation.schemas import MoonshotChatIn, MoonshotChatOut, OllamaChatIn, OllamaChatOut
from apps.core.infrastructure.throttling import rate_limit_from_settings
from .performance_monitor_api import router as performance_router

router = Router(tags=["Main API"])


def _get_ai_service() -> Any:
    from apps.core.dependencies.automation_adapters import build_ai_service

    return build_ai_service()


def _get_document_processor_service() -> Any:
    from apps.core.dependencies.automation_adapters import build_document_processing_service

    return build_document_processing_service()


def _get_config_service() -> Any:
    from apps.core.dependencies.automation_adapters import build_automation_config_service

    return build_automation_config_service()


# 添加性能监控子路由
router.add_router("/performance", performance_router)

# ============================================================================
# AI集成API
# ============================================================================


@router.post("/ai/ollama", response=OllamaChatOut)
def ai_ollama(request: Any, payload: OllamaChatIn) -> OllamaChatOut:
    """Ollama AI接口"""
    # 使用工厂函数获取服务
    service = _get_ai_service()

    # 调用服务处理Ollama聊天
    result = service.chat_with_ollama(model=payload.model, prompt=payload.prompt, text=payload.text)

    return OllamaChatOut(data=result)


@router.post("/ai/moonshot", response=MoonshotChatOut)
def ai_moonshot(request: Any, payload: MoonshotChatIn) -> MoonshotChatOut:
    """Moonshot AI接口"""
    # 使用工厂函数获取服务
    service = _get_ai_service()

    # 调用服务处理Moonshot聊天
    result = service.chat_with_moonshot(model=payload.model, prompt=payload.prompt, text=payload.text)

    return MoonshotChatOut(data=result)


# ============================================================================
# 通用工具API
# ============================================================================


@router.post("/file/upload", response=dict)
@rate_limit_from_settings("UPLOAD")
def upload_file(
    request: Any,
    file: UploadedFile = File(...),  # type: ignore[arg-type]
    limit: int | None = None,
    preview_page: int | None = None,
) -> dict[str, Any]:
    """通用文件上传和预处理API"""
    # 使用工厂函数获取服务
    service = _get_document_processor_service()

    # 调用服务处理文件上传
    result = service.process_uploaded_file(uploaded_file=file, limit=limit, preview_page=preview_page)

    return {
        "success": result.success,
        "file_info": result.file_info,
        "extraction": result.extraction,
        "processing_params": result.processing_params,
        "error": result.error,
    }


# ============================================================================
# 配置和状态API
# ============================================================================


@router.get("/config")
@rate_limit_from_settings("ADMIN")
def get_config(request: Any) -> Any:
    """获取当前配置信息"""
    from apps.core.security.admin_access import ensure_admin_request

    ensure_admin_request(request)
    # 使用工厂函数获取服务
    service = _get_config_service()

    # 调用服务获取配置信息
    config = service.get_automation_config()

    return config


@router.get("/status")
def get_status(request: Any) -> Any:
    """获取系统状态"""
    # 使用工厂函数获取服务
    service = _get_config_service()

    # 调用服务获取系统状态
    status = service.get_system_status()

    return status
