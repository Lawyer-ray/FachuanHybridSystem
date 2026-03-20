"""Module for factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.conf import settings

from apps.core.llm.config import LLMConfig

from .interfaces import IAgentFactory
from .llm_provider import LitigationLLMProvider

logger = logging.getLogger("apps.litigation_ai")


class LitigationAgent:
    """诉讼文书生成 Agent。"""

    def __init__(
        self,
        llm: Any,
        tools: list[Any],
        system_prompt: str,
        session_id: str,
        case_id: int,
        max_iterations: int = 10,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.tools_map = {tool.name: tool for tool in tools if hasattr(tool, "name")}
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.case_id = case_id
        self.max_iterations = max_iterations

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history: list[dict[str, Any]] = []

        for iteration in range(self.max_iterations):
            response = self.llm.invoke(messages)
            tool_calls = list(getattr(response, "tool_calls", []) or [])
            assistant_message = {
                "role": "assistant",
                "content": str(getattr(response, "content", "") or ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            if not tool_calls:
                break

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("name", "") or "")
                tool_args = tool_call.get("args", {})

                logger.info(
                    "执行工具调用",
                    extra={
                        "session_id": self.session_id,
                        "tool_name": tool_name,
                        "iteration": iteration,
                    },
                )

                tool_result = self._execute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tool_call.get("id", ""),
                    }
                )

        return {
            "messages": messages,
            "tool_calls": tool_calls_history,
        }

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history: list[dict[str, Any]] = []

        for iteration in range(self.max_iterations):
            response = await self.llm.ainvoke(messages)
            tool_calls = list(getattr(response, "tool_calls", []) or [])
            assistant_message = {
                "role": "assistant",
                "content": str(getattr(response, "content", "") or ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            if not tool_calls:
                break

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("name", "") or "")
                tool_args = tool_call.get("args", {})

                logger.info(
                    "执行工具调用",
                    extra={
                        "session_id": self.session_id,
                        "tool_name": tool_name,
                        "iteration": iteration,
                    },
                )

                tool_result = await self._aexecute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tool_call.get("id", ""),
                    }
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
        messages = self._prepare_messages(state.get("messages", []))
        tool_calls_history: list[dict[str, Any]] = []

        for _iteration in range(self.max_iterations):
            full_content = ""
            tool_calls: list[dict[str, Any]] = []

            async for chunk in self.llm.astream(messages):
                content = str(getattr(chunk, "content", "") or "")
                if content:
                    full_content += content
                    if stream_callback:
                        await stream_callback(content)

                chunk_tool_calls = getattr(chunk, "tool_calls", None)
                if chunk_tool_calls:
                    tool_calls.extend(list(chunk_tool_calls))

            assistant_message = {
                "role": "assistant",
                "content": full_content,
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            if not tool_calls:
                break

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("name", "") or "")
                tool_args = tool_call.get("args", {})

                tool_result = await self._aexecute_tool(tool_name, tool_args)
                tool_calls_history.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tool_call.get("id", ""),
                    }
                )

        return {
            "messages": messages,
            "tool_calls": tool_calls_history,
        }

    def _prepare_messages(self, input_messages: list[Any]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]

        for msg in input_messages:
            if isinstance(msg, dict):
                role = str(msg.get("role", "user") or "user")
                content = str(msg.get("content", "") or "")
            else:
                role = str(getattr(msg, "role", getattr(msg, "type", "user")) or "user")
                content = str(getattr(msg, "content", "") or "")

            if role == "ai":
                role = "assistant"
            if role == "system":
                continue
            if role not in {"user", "assistant", "tool"}:
                role = "user"
            messages.append({"role": role, "content": content})

        return messages

    def _execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
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
        if tool_name not in self.tools_map:
            return {"error": f"未知工具: {tool_name}"}

        tool = self.tools_map[tool_name]
        try:
            if hasattr(tool, "ainvoke"):
                return await tool.ainvoke(tool_args)
            from asgiref.sync import sync_to_async

            return await sync_to_async(tool.invoke, thread_sensitive=True)(tool_args)
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
    """诉讼文书生成 Agent 工厂。"""

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        summarization_token_threshold: int | None = None,
        preserve_messages: int | None = None,
        max_iterations: int | None = None,
    ) -> None:
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
        agent_tools = tools if tools is not None else self._get_default_tools(case_id)
        llm = self._create_llm_with_tools(agent_tools)
        system_prompt = self._get_system_prompt()

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
        temperature = self._temperature if self._temperature is not None else 0.7
        return self._llm_provider.create_llm(model=self._model, temperature=temperature)

    def _create_llm_with_tools(self, tools: list[Any]) -> Any:
        temperature = self._temperature if self._temperature is not None else 0.7
        return self._llm_provider.create_llm_with_tools(
            tools=tools,
            model=self._model,
            temperature=temperature,
        )

    def _get_default_tools(self, case_id: int) -> list[Any]:
        from .tools import get_litigation_tools

        return get_litigation_tools(case_id)

    def _get_system_prompt(self) -> str:
        from .prompts import get_system_prompt

        return get_system_prompt()

    def _create_middleware(self, session_id: str, llm: Any) -> list[Any]:
        from .middleware import LitigationMemoryMiddleware, LitigationSummarizationMiddleware, SummarizationConfig

        _ = llm

        preserve_messages = self._preserve_messages if self._preserve_messages is not None else 10
        memory_middleware = LitigationMemoryMiddleware(
            session_id=session_id,
            max_messages=preserve_messages * 2,
        )

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
        if self._model:
            return self._model
        return LLMConfig.get_default_model()

    def get_config(self) -> dict[str, Any]:
        return {
            "model": self.get_model_name(),
            "temperature": self._temperature,
            "summarization_token_threshold": self._summarization_token_threshold,
            "preserve_messages": self._preserve_messages,
            "max_iterations": self._max_iterations,
        }
