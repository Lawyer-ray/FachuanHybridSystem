"""
诉讼 Agent 接口定义

定义 Agent 服务和工厂的抽象接口,支持依赖注入和测试.

Requirements: 1.1, 8.1
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class ILitigationAgentService(ABC):
    """
    诉讼 Agent 服务接口

    定义 Agent 服务的核心方法,用于处理用户消息和证据选择.
    """

    @abstractmethod
    async def handle_message(
        self,
        session_id: str,
        case_id: int,
        user_message: str,
        metadata: dict[str, Any] | None = None,
        stream_callback: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        """
        处理用户消息

        Args:
            session_id: 会话 ID
            case_id: 案件 ID
            user_message: 用户消息内容
            metadata: 消息元数据(可选)
            stream_callback: 流式响应回调(可选)

        Returns:
            响应字典,包含 type、content、metadata 字段
        """
        pass

    @abstractmethod
    async def handle_evidence_selection(
        self,
        session_id: str,
        case_id: int,
        evidence_item_ids: list[int],
        our_evidence_item_ids: list[int],
        opponent_evidence_item_ids: list[int],
    ) -> dict[str, Any]:
        """
        处理证据选择

        Args:
            session_id: 会话 ID
            case_id: 案件 ID
            evidence_item_ids: 所有选中的证据项 ID
            our_evidence_item_ids: 我方证据项 ID
            opponent_evidence_item_ids: 对方证据项 ID

        Returns:
            响应字典
        """
        pass

    @abstractmethod
    def cleanup_agent(self, session_id: str) -> None:
        """
        清理 Agent 实例

        Args:
            session_id: 会话 ID
        """
        pass


class IAgentFactory(ABC):
    """
    Agent 工厂接口

    定义创建 Agent 实例的抽象方法.
    """

    @abstractmethod
    def create_agent(
        self,
        session_id: str,
        case_id: int,
        tools: list[Any] | None = None,
    ) -> Any:
        """
        创建 Agent 实例

        Args:
            session_id: 会话 ID
            case_id: 案件 ID
            tools: 自定义工具列表(可选)

        Returns:
            配置好的 Agent 实例
        """
        pass


class IMemoryMiddleware(ABC):
    """
    Memory 中间件接口

    定义对话历史管理的抽象方法.
    """

    @abstractmethod
    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        """
        Agent 执行前的钩子,用于加载历史消息

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            修改后的状态,或 None 表示不修改
        """
        pass

    @abstractmethod
    def after_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        """
        Agent 执行后的钩子,用于保存新消息

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            修改后的状态,或 None 表示不修改
        """
        pass
