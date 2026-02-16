"""Module for factory."""

from __future__ import annotations

"""
诉讼文书生成 Agent 工厂

负责创建和配置 LangChain Agent 实例.
使用 langchain-openai 的 ChatOpenAI.bind_tools() 实现工具调用能力.

Requirements: 1.1, 1.2, 1.5, 8.1
"""

import logging
from collections.abc import Callable
from typing import Any

from django.conf import settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .interfaces import IAgentFactory
from .llm_provider import LitigationLLMProvider

logger = logging.getLogger("apps.litigation_ai")


class LitigationAgent:
    """
    诉讼文书生成 Agent

    封装 LangChain ChatOpenAI 的工具调用能力,实现 ReAct 风格的 Agent.
    支持同步和异步调用,支持流式输出.

    Attributes:
        llm: 绑定了工具的 ChatOpenAI 实例
        tools: 工具列表
        tools_map: 工具名称到工具函数的映射
        system_prompt: 系统提示词
        session_id: 会话 ID
        case_id: 案件 ID
        max_iterations: 最大迭代次数(防止无限循环)
    """

    def __init__(
        self,
        llm: Any,
        tools: list[Any],
        system_prompt: str,
        session_id: str,
        case_id: int,
        max_iterations: int = 10,
    ) -> None:
        """
        初始化 Agent

        Args:
            llm: 绑定了工具的 ChatOpenAI 实例
            tools: 工具列表
            system_prompt: 系统提示词
            session_id: 会话 ID
            case_id: 案件 ID
            max_iterations: 最大迭代次数
        """
        self.llm = llm
        self.tools = tools
        self.tools_map = {tool.name: tool for tool in tools}
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.case_id = case_id
        self.max_iterations = max_iterations

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        同步调用 Agent

        实现 ReAct 循环:推理: state: 输入状态,包含 messages 字段

        Returns:
            更新后的状态,包含 Agent 响应和工具调用记录
        """
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history = []

        for iteration in range(self.max_iterations):
            # 调用 LLM
            response = self.llm.invoke(messages)
            messages.append(response)

            # 检查是否有工具调用
            if not response.tool_calls:
                # 没有工具调用,返回最终响应
                break

            # 执行工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                logger.info(
                    "执行工具调用",
                    extra={
                        "session_id": self.session_id,
                        "tool_name": tool_name,
                        "iteration": iteration,
                    },
                )

                # 执行工具
                tool_result = self._execute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )

                # 添加工具结果到消息
                from langchain_core.messages import ToolMessage

                messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    )
                )

        # 构建返回状态
        return {
            "messages": messages,
            "tool_calls": tool_calls_history,
        }

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        异步调用 Agent

        Args:
            state: 输入状态

        Returns:
            更新后的状态
        """
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history = []

        for iteration in range(self.max_iterations):
            # 异步调用 LLM
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            # 检查是否有工具调用
            if not response.tool_calls:
                break

            # 执行工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                logger.info(
                    "执行工具调用",
                    extra={
                        "session_id": self.session_id,
                        "tool_name": tool_name,
                        "iteration": iteration,
                    },
                )

                # 执行工具(工具本身可能是同步的)
                tool_result = await self._aexecute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )

                # 添加工具结果到消息
                from langchain_core.messages import ToolMessage

                messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    )
                )

        return {
            "messages": messages,
            "tool_calls": tool_calls_history,
        }

    async def astream(
        self,
        state: dict[str, Any],
        stream_callback: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        """
        异步流式调用 Agent

        Args:
            state: 输入状态
            stream_callback: 流式输出回调函数

        Returns:
            更新后的状态
        """
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history = []

        for _iteration in range(self.max_iterations):
            # 流式调用 LLM
            full_content = ""
            tool_calls = []

            async for chunk in self.llm.astream(messages):
                # 处理内容
                if chunk.content:
                    full_content += chunk.content
                    if stream_callback:
                        await stream_callback(chunk.content)

                # 收集工具调用
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)

            # 构建完整的 AI 消息
            response = AIMessage(content=full_content, tool_calls=tool_calls)
            messages.append(response)

            # 检查是否有工具调用
            if not tool_calls:
                break

            # 执行工具调用
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                tool_result = await self._aexecute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )

                from langchain_core.messages import ToolMessage

                messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    )
                )

        return {
            "messages": messages,
            "tool_calls": tool_calls_history,
        }

    def _prepare_messages(self, input_messages: list[Any]) -> list[Any]:
        """
        准备消息列表,添加系统提示词

        Args:
            input_messages: 输入消息列表

        Returns:
            包含系统提示词的消息列表
        """
        from langchain_core.messages import BaseMessage

        messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]

        for msg in input_messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
                elif role == "system":
                    # 系统消息已添加,跳过
                    pass
            else:
                # 已经是 LangChain 消息对象
                messages.append(msg)

        return messages

    def _execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            tool_args: 工具参数

        Returns:
            工具执行结果
        """
        if tool_name not in self.tools_map:
            return {"error": f"未知工具: {tool_name}"}

        tool = self.tools_map[tool_name]
        try:
            return tool.invoke(tool_args)
        except Exception as e:
            logger.error(
                "工具执行失败",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                },
            )
            return {"error": f"工具执行失败: {e!s}"}

    async def _aexecute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        """
        异步执行工具调用

        Args:
            tool_name: 工具名称
            tool_args: 工具参数

        Returns:
            工具执行结果
        """
        if tool_name not in self.tools_map:
            return {"error": f"未知工具: {tool_name}"}

        tool = self.tools_map[tool_name]
        try:
            # 尝试异步调用,如果不支持则同步调用
            if hasattr(tool, "ainvoke"):
                return await tool.ainvoke(tool_args)
            else:
                from asgiref.sync import sync_to_async

                return await sync_to_async(tool.invoke)(tool_args)
        except Exception as e:
            logger.error(
                "工具执行失败",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                },
            )
            return {"error": f"工具执行失败: {e!s}"}


class LitigationAgentFactory(IAgentFactory):
    """
    诉讼文书生成 Agent 工厂

    使用 LangChain ChatOpenAI.bind_tools() 创建支持工具调用的 Agent.
    支持可配置的模型选择和 Middleware 配置.

    Attributes:
        _model: 使用的 LLM 模型名称
        _temperature: LLM 温度参数
        _summarization_token_threshold: 触发摘要的 token 阈值
        _preserve_messages: 摘要时保留的最近消息数量
        _max_iterations: Agent 最大迭代次数
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        summarization_token_threshold: int | None = None,
        preserve_messages: int | None = None,
        max_iterations: int | None = None,
    ) -> None:
        """
        初始化 Agent 工厂

        Args:
            model: LLM 模型名称,默认从 settings 或 LLMConfig 读取
            temperature: LLM 温度参数,默认 0.7
            summarization_token_threshold: 摘要触发阈值,默认从 settings 读取
            preserve_messages: 保留消息数量,默认从 settings 读取
            max_iterations: Agent 最大迭代次数,默认 10
        """
        self._model = model or getattr(settings, "LITIGATION_AGENT_MODEL", None)
        self._temperature = temperature or getattr(settings, "LITIGATION_AGENT_TEMPERATURE", 0.7)
        self._summarization_token_threshold = summarization_token_threshold or getattr(
            settings, "LITIGATION_AGENT_SUMMARIZATION_THRESHOLD", 2000
        )
        self._preserve_messages = preserve_messages or getattr(settings, "LITIGATION_AGENT_PRESERVE_MESSAGES", 10)
        self._max_iterations = max_iterations or getattr(settings, "LITIGATION_AGENT_MAX_ITERATIONS", 10)
        self._llm_provider = LitigationLLMProvider()

    def create_agent(
        self,
        session_id: str,
        case_id: int,
        tools: list[Any] | None = None,
    ) -> LitigationAgent:
        """
        创建配置好的 Agent 实例

        使用 ChatOpenAI.bind_tools() 绑定工具,创建支持工具调用的 Agent.

        Args:
            session_id: 会话 ID,用于 Memory 持久化
            case_id: 案件 ID,用于工具调用
            tools: 自定义工具列表,默认使用标准诉讼工具集

        Returns:
            配置好的 LitigationAgent 实例

        Raises:
            ValidationException: 配置无效时抛出
        """
        # 获取工具集
        agent_tools = tools if tools is not None else self._get_default_tools(case_id)

        # 创建 LLM 实例并绑定工具
        llm = self._create_llm_with_tools(agent_tools)

        # 获取系统提示词
        system_prompt = self._get_system_prompt()

        # 记录日志
        model_name = self.get_model_name()
        logger.info(
            "创建 Agent 实例",
            extra={
                "session_id": session_id,
                "case_id": case_id,
                "model": model_name,
                "tools_count": len(agent_tools),
                "max_iterations": self._max_iterations,
            },
        )

        # 创建并返回 Agent
        max_iterations = self._max_iterations if self._max_iterations is not None else 10
        return LitigationAgent(
            llm=llm,
            tools=agent_tools,
            system_prompt=system_prompt,
            session_id=session_id,
            case_id=case_id,
            max_iterations=max_iterations,
        )

    def _create_llm(self) -> Any:
        """
        创建基础 LLM 实例

        Returns:
            配置好的 ChatOpenAI 实例
        """
        temperature = self._temperature if self._temperature is not None else 0.7
        return self._llm_provider.create_llm(model=self._model, temperature=temperature)

    def _create_llm_with_tools(self, tools: list[Any]) -> Any:
        """
        创建绑定了工具的 LLM 实例

        Args:
            tools: 工具列表

        Returns:
            绑定了工具的 ChatOpenAI 实例
        """
        temperature = self._temperature if self._temperature is not None else 0.7
        return self._llm_provider.create_llm_with_tools(
            tools=tools,
            model=self._model,
            temperature=temperature,
        )

    def _get_default_tools(self, case_id: int) -> list[Any]:
        """
        获取默认工具集

        Args:
            case_id: 案件 ID

        Returns:
            工具列表
        """
        from .tools import get_litigation_tools

        return get_litigation_tools(case_id)

    def _get_system_prompt(self) -> str:
        """
        获取系统提示词

        Returns:
            系统提示词字符串
        """
        from .prompts import get_system_prompt

        return get_system_prompt()

    def _create_middleware(self, session_id: str, llm: Any) -> list[Any]:
        """
        创建 Middleware 列表

        Args:
            session_id: 会话 ID
            llm: LLM 实例

        Returns:
            Middleware 列表
        """
        from .middleware import LitigationMemoryMiddleware, LitigationSummarizationMiddleware, SummarizationConfig

        # Memory 中间件
        preserve_messages = self._preserve_messages if self._preserve_messages is not None else 10
        memory_middleware = LitigationMemoryMiddleware(
            session_id=session_id,
            max_messages=preserve_messages * 2,  # 加载更多历史以便摘要
        )

        # 摘要中间件
        token_threshold = (
            self._summarization_token_threshold if self._summarization_token_threshold is not None else 2000
        )
        summarization_config = SummarizationConfig(
            token_threshold=token_threshold,
            preserve_messages=preserve_messages,
            model=self._model,
        )
        summarization_middleware = LitigationSummarizationMiddleware(
            session_id=session_id,
            config=summarization_config,
        )

        return [memory_middleware, summarization_middleware]

    def get_model_name(self) -> str:
        """
        获取当前使用的模型名称

        Returns:
            模型名称
        """
        from apps.litigation_ai.services.wiring import get_llm_service

        if self._model:
            return self._model

        llm_service = get_llm_service()
        llm = llm_service.get_langchain_llm()
        return getattr(llm, "model", "") or getattr(llm, "model_name", "") or ""

    def get_config(self) -> dict[str, Any]:
        """
        获取工厂配置信息

        Returns:
            配置字典
        """
        return {
            "model": self.get_model_name(),
            "temperature": self._temperature,
            "summarization_token_threshold": self._summarization_token_threshold,
            "preserve_messages": self._preserve_messages,
            "max_iterations": self._max_iterations,
        }
