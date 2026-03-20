"""
诉讼文书生成 Agent 模块

基于统一 LLM 服务的 Agent 架构,实现智能诉讼文书生成.

主要组件:
- LitigationAgent: Agent 实例,封装 LLM 和工具调用
- LitigationAgentFactory: Agent 工厂,创建和配置 Agent 实例
- LitigationAgentState: Agent 状态定义
- ILitigationAgentService: Agent 服务接口
- IAgentFactory: Agent 工厂接口
- Tools: Agent 工具集
- Middleware: 对话历史和摘要中间件
- Prompts: 系统提示词
"""

from .factory import LitigationAgent, LitigationAgentFactory
from .interfaces import IAgentFactory, ILitigationAgentService, IMemoryMiddleware
from .middleware import LitigationMemoryMiddleware, LitigationSummarizationMiddleware, SummarizationConfig
from .prompts import build_full_prompt, get_system_prompt
from .schemas import AgentResponse, DraftOutput, ToolCallRecord
from .state import LitigationAgentState
from .tools import get_litigation_tools

__all__ = [
    # Agent
    "LitigationAgent",
    # 工厂
    "LitigationAgentFactory",
    # 状态
    "LitigationAgentState",
    # 接口
    "ILitigationAgentService",
    "IAgentFactory",
    "IMemoryMiddleware",
    # 数据结构
    "AgentResponse",
    "DraftOutput",
    "ToolCallRecord",
    # 工具
    "get_litigation_tools",
    # 中间件
    "LitigationMemoryMiddleware",
    "LitigationSummarizationMiddleware",
    "SummarizationConfig",
    # 提示词
    "get_system_prompt",
    "build_full_prompt",
]
