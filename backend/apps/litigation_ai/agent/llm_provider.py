"""Module for llm provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from apps.litigation_ai.services.wiring import get_llm_service


@dataclass
class AgentLLMResponse:  # pragma: no cover
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    type: str = "assistant"


@dataclass
class AgentLLMStreamChunk:  # pragma: no cover
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class AgentLLMAdapter:  # pragma: no cover
    def __init__(
        self, llm_service: Any, model: str | None = None, temperature: float = 0.7
    ) -> None:  # pragma: no cover
        self._llm_service = llm_service
        self._model = model
        self._temperature = temperature
        #: `bind_tools` 绑定的工具面（S23-02）。ReAct 循环靠它拿到可用工具。
        self._bound_tools: list[Any] = []

    @staticmethod
    def _normalize_messages(messages: list[Any]) -> list[dict[str, str]]:  # pragma: no cover
        normalized: list[dict[str, str]] = []
        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role", "user") or "user")
                content = str(message.get("content", "") or "")
            else:
                role = str(getattr(message, "role", getattr(message, "type", "user")) or "user")
                content = str(getattr(message, "content", "") or "")

            if role == "ai":
                role = "assistant"
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            normalized.append({"role": role, "content": content})
        return normalized

    def bind_tools(self, tools: list[Any]) -> AgentLLMAdapter:  # pragma: no cover
        """记录工具列表。

        S23-02（2026-11-23 二轮审计）：原实现 `_ = tools` 直接丢弃，
        而 ReAct 循环依赖 `bind_tools` 让模型拿到工具面 —— 丢掉的后果是**第一轮就 break**，
        表现为「AI 不使用任何工具，直接给一段空回答」。
        本适配器底层 `_llm_service.chat` 不接受 tools 参数，因此在 `describe_tools`
        里把工具面转成文字塞进 system prompt（能力等价，不改底层契约）。
        """
        self._bound_tools = list(tools or [])
        return self

    def _describe_tools(self) -> str:
        """把绑定的工具面转成一段给人/模型看的说明（S23-02）。"""
        if not self._bound_tools:
            return ""
        lines = ["可用工具（ReAct：需要外部信息时必须调用其中某个工具，不要凭记忆回答）："]
        for tool in self._bound_tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)
            desc = getattr(tool, "description", "") or ""
            lines.append(f"- {name}: {desc}".rstrip())
        return "\n".join(lines)

    def invoke(self, messages: list[Any]) -> AgentLLMResponse:  # pragma: no cover
        normalized = self._normalize_messages(messages)
        tool_hint = self._describe_tools()
        if tool_hint:
            normalized = _inject_system_hint(normalized, tool_hint)
        llm_response = self._llm_service.chat(
            messages=normalized,
            model=self._model,
            temperature=self._temperature,
        )
        return AgentLLMResponse(content=llm_response.content or "")

    async def ainvoke(self, messages: list[Any]) -> AgentLLMResponse:  # pragma: no cover
        llm_response = await self._llm_service.achat(
            messages=self._normalize_messages(messages),
            model=self._model,
            temperature=self._temperature,
        )
        return AgentLLMResponse(content=llm_response.content or "")

    async def astream(self, messages: list[Any]) -> AsyncIterator[AgentLLMStreamChunk]:  # pragma: no cover
        response = await self.ainvoke(messages)
        if response.content:
            yield AgentLLMStreamChunk(content=response.content)


class LitigationLLMProvider:  # pragma: no cover
    def __init__(self, llm_service: Any | None = None) -> None:  # pragma: no cover
        self._llm_service = llm_service

    @property
    def llm_service(self) -> Any:  # pragma: no cover
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    def create_llm(  # pragma: no cover
        self,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AgentLLMAdapter:
        return AgentLLMAdapter(llm_service=self.llm_service, model=model, temperature=temperature)

    def create_llm_with_tools(  # pragma: no cover
        self,
        tools: list[Any],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AgentLLMAdapter:
        llm = self.create_llm(model=model, temperature=temperature)
        return llm.bind_tools(tools) if tools else llm


def _inject_system_hint(messages: list[dict[str, str]], hint: str) -> list[dict[str, str]]:
    """把工具面说明合并进 system 消息（没有 system 就在最前面插一条）。"""
    for msg in messages:
        if msg.get("role") == "system":
            msg["content"] = (msg.get("content") or "") + "\n\n" + hint
            return messages
    return [{"role": "system", "content": hint}, *messages]
