"""
LLM 后端基础定义

定义 LLM 后端的统一接口和数据类.

Requirements: 1.1, 1.5
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    """
    LLM 响应数据类

    统一所有后端的响应格式,便于调用方处理.

    Attributes:
        content: 生成的文本内容
        model: 使用的模型名称
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        total_tokens: 总 token 数
        duration_ms: 调用耗时(毫秒)
        backend: 使用的后端标识 (siliconflow/ollama/moonshot)

    Requirements: 1.1, 1.5
    """

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: float
    backend: str = ""


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMStreamChunk:
    content: str = ""
    usage: LLMUsage | None = None
    model: str = ""
    backend: str = ""


@dataclass
class BackendConfig:
    """
    后端配置数据类

    定义 LLM 后端的配置参数.

    Attributes:
        name: 后端名称 (siliconflow/ollama/moonshot)
        enabled: 是否启用
        priority: 降级优先级,数字越小优先级越高
        default_model: 默认模型名称
        base_url: API 基础 URL
        api_key: API 密钥
        timeout: 请求超时时间(秒)
        extra_options: 额外配置选项
    """

    name: str
    enabled: bool
    priority: int
    default_model: str
    base_url: str | None = None
    api_key: str | None = None
    timeout: int = 60
    extra_options: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ILLMBackend(Protocol):
    """
    LLM 后端接口协议

    定义所有 LLM 后端必须实现的方法.使用 Protocol 实现结构化子类型,
    无需显式继承即可满足接口约束.

    Requirements: 1.1, 1.5
    """

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        同步聊天接口

        Args:
            messages: 消息列表,格式为 [{"role": "user", "content": "..."}]
            model: 模型名称,None 时使用默认模型
            temperature: 温度参数,控制输出随机性
            max_tokens: 最大输出 token 数
            **kwargs: 后端特定参数

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        ...

    async def achat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        异步聊天接口

        Args:
            messages: 消息列表,格式为 [{"role": "user", "content": "..."}]
            model: 模型名称,None 时使用默认模型
            temperature: 温度参数,控制输出随机性
            max_tokens: 最大输出 token 数
            **kwargs: 后端特定参数

        Returns:
            LLMResponse: 统一格式的响应对象

        Raises:
            LLMNetworkError: 网络连接失败
            LLMAPIError: API 返回错误
            LLMAuthenticationError: 认证失败
            LLMTimeoutError: 请求超时
        """
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[LLMStreamChunk]: ...

    async def astream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]: ...

    def get_default_model(self) -> str:
        """
        获取默认模型名称

        Returns:
            str: 后端的默认模型名称
        """
        ...

    def is_available(self) -> bool:
        """
        检查后端是否可用

        检查后端的配置是否完整(如 API Key 是否存在),
        以及服务是否可达.

        Returns:
            bool: True 表示后端可用,False 表示不可用
        """
        ...
