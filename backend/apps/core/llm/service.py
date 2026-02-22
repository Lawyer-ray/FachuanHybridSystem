"""
统一 LLM 服务层

提供统一的 LLM 调用接口,支持多后端选择和降级逻辑.

Requirements: 1.2, 1.4, 1.5
"""

import logging
from typing import Any, ClassVar, cast

from .backends import BackendConfig, ILLMBackend, LLMResponse, MoonshotBackend, OllamaBackend
from .client import LLMClient
from .fallback_policy import LLMFallbackPolicy
from .router import LLMBackendRouter

logger = logging.getLogger("apps.core.llm.service")


class LLMService:
    """
    统一 LLM 服务

    提供统一的 LLM 调用接口,支持:
    - 多后端选择(siliconflow/ollama/moonshot)
    - 自动降级(按优先级尝试可用后端)
    - 统一的响应格式

    Example:
        service = LLMService()

        # 使用默认后端
        response = service.complete("你好")

        # 指定后端
        response = service.complete("你好", backend="ollama")

        # 禁用降级
        response = service.complete("你好", fallback=False)

    Requirements: 1.2, 1.4, 1.5
    """

    # 后端名称常量
    BACKEND_SILICONFLOW = "siliconflow"
    BACKEND_OLLAMA = "ollama"
    BACKEND_MOONSHOT = "moonshot"

    # 默认后端优先级(数字越小优先级越高)
    DEFAULT_PRIORITIES: ClassVar = {
        BACKEND_SILICONFLOW: 1,
        BACKEND_OLLAMA: 2,
        BACKEND_MOONSHOT: 3,
    }

    def __init__(
        self,
        backend_configs: dict[str, BackendConfig] | None = None,
        default_backend: str | None = None,
    ) -> None:
        """
        初始化 LLM 服务

        Args:
            backend_configs: 后端配置字典,键为后端名称
            default_backend: 默认后端名称,None 时使用 siliconflow
        """
        self._backend_configs = backend_configs
        self._default_backend = default_backend or self.BACKEND_SILICONFLOW
        self._router = LLMBackendRouter(backend_configs=backend_configs)
        self._fallback_policy = LLMFallbackPolicy(router=self._router)
        self._client = LLMClient(default_backend=self._default_backend)

    def _get_backend_config(self, name: str) -> BackendConfig:
        """
        获取后端配置

        Args:
            name: 后端名称

        Returns:
            BackendConfig 配置对象
        """
        return self._router.get_backend_config(name)

    def _get_backend(self, name: str) -> ILLMBackend:
        """
        获取后端实例(延迟初始化)

        Args:
            name: 后端名称

        Returns:
            ILLMBackend 后端实例

        Raises:
            ValueError: 未知的后端名称
        """
        return self._router.get_backend(name)

    def _get_backends_by_priority(self) -> list[tuple[str, ILLMBackend]]:
        """
        按优先级获取所有后端

        Returns:
            (后端名称, 后端实例) 元组列表,按优先级排序
        """
        return self._router.get_backends_by_priority()

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """
        简化的补全接口

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            backend: 指定后端 (siliconflow/ollama/moonshot),None 使用默认
            model: 指定模型,None 使用后端默认模型
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            fallback: 是否启用降级

        Returns:
            LLMResponse 响应对象

        Requirements: 1.2, 1.4, 1.5
        """
        return self._client.complete(
            fallback_policy=self._fallback_policy,
            prompt=prompt,
            system_prompt=system_prompt,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """
        聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            backend: 指定后端 (siliconflow/ollama/moonshot),None 使用默认
            model: 指定模型,None 使用后端默认模型
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            fallback: 是否启用降级

        Returns:
            LLMResponse 响应对象

        Requirements: 1.2, 1.4, 1.5
        """
        return self._client.chat(
            fallback_policy=self._fallback_policy,
            messages=messages,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    async def achat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """
        异步聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            backend: 指定后端 (siliconflow/ollama/moonshot),None 使用默认
            model: 指定模型,None 使用后端默认模型
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            fallback: 是否启用降级

        Returns:
            LLMResponse 响应对象
        """
        return await self._client.achat(
            fallback_policy=self._fallback_policy,
            messages=messages,
            backend=backend,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    def get_langchain_llm(
        self,
        backend: str | None = None,
        model: str | None = None,
    ) -> Any:
        """
        获取 LangChain LLM 实例

        用于构建复杂的 LCEL 链.

        Args:
            backend: 指定后端,None 使用默认后端
            model: 指定模型,None 使用后端默认模型

        Returns:
            LangChain LLM 实例(ChatOpenAI 或兼容类型)

        Raises:
            ValueError: 后端不支持 LangChain

        Requirements: 1.5
        """
        backend_name = backend or self._default_backend
        backend_instance = self._get_backend(backend_name)

        # 检查后端是否支持 get_langchain_llm
        if not hasattr(backend_instance, "get_langchain_llm"):
            raise ValueError(f"后端 {backend_name} 不支持 LangChain LLM")

        return backend_instance.get_langchain_llm(model=model)

    def get_structured_llm(
        self,
        schema: type,
        backend: str | None = None,
        model: str | None = None,
        method: str = "json_mode",
    ) -> Any:
        """
        获取结构化输出 LLM

        使用 with_structured_output 方法绑定 Pydantic 模型,
        让 LLM 直接返回结构化数据.

        Args:
            schema: Pydantic 模型类,定义输出结构
            backend: 指定后端,None 使用默认后端
            model: 指定模型,None 使用后端默认模型
            method: 结构化输出方法 (json_mode/function_calling/json_schema)

        Returns:
            绑定了结构化输出的 Runnable 实例

        Raises:
            ValueError: 后端不支持结构化输出

        Requirements: 1.5
        """
        backend_name = backend or self._default_backend
        backend_instance = self._get_backend(backend_name)

        # 检查后端是否支持 get_structured_llm
        if not hasattr(backend_instance, "get_structured_llm"):
            raise ValueError(f"后端 {backend_name} 不支持结构化输出")

        return backend_instance.get_structured_llm(
            schema=schema,
            model=model,
            method=method,
        )

    def get_backend(self, name: str) -> ILLMBackend:
        """
        获取指定后端实例

        用于直接访问后端特有功能(如 Moonshot 的文件操作).

        Args:
            name: 后端名称

        Returns:
            ILLMBackend 后端实例
        """
        return self._get_backend(name)


# 模块级单例(延迟初始化)
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
