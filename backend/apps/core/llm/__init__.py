"""
LLM 抽象层模块

提供统一的 LLM 调用抽象,支持多种模型选择,包含 Prompt 管理机制.
用于对接硅基流动(SiliconFlow)的统一大模型 API 接口.

主要组件:
- LLMConfig: 配置管理
- LLMService: 业务服务层
- PromptManager: Prompt 模板管理器

使用示例:
    from apps.core.interfaces import ServiceLocator

    llm_service = ServiceLocator.get_llm_service()
    response = llm_service.complete("你好")
"""

from .backends import LLMResponse
from .config import LLMConfig
from .exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMBackendUnavailableError,
    LLMError,
    LLMNetworkError,
    LLMTimeoutError,
)
from .prompts import CodePromptTemplate, PromptManager
from .service import LLMService, get_llm_service

__all__ = [
    # 配置
    "LLMConfig",
    "LLMResponse",
    # 服务
    "LLMService",
    "LLMBackendUnavailableError",
    "get_llm_service",
    # 异常
    "LLMError",
    "LLMNetworkError",
    "LLMAPIError",
    "LLMAuthenticationError",
    "LLMTimeoutError",
    # Prompt
    "PromptManager",
    "CodePromptTemplate",
]
