"""Module for llm provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from apps.litigation_ai.services.wiring import get_llm_service


@dataclass
class AgentLLMResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    type: str = "assistant"


@dataclass
class AgentLLMStreamChunk:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class AgentLLMAdapter:
    def __init__(self, llm_service: Any, model: str | None = None, temperature: float = 0.7) -> None:
        self._llm_service = llm_service
        self._model = model
        self._temperature = temperature

    @staticmethod
    def _normalize_messages(messages: list[Any]) -> list[dict[str, str]]:
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

    def bind_tools(self, tools: list[Any]) -> AgentLLMAdapter:
        _ = tools
        return self

    def invoke(self, messages: list[Any]) -> AgentLLMResponse:
        llm_response = self._llm_service.chat(
            messages=self._normalize_messages(messages),
            model=self._model,
            temperature=self._temperature,
        )
        return AgentLLMResponse(content=llm_response.content or "")

    async def ainvoke(self, messages: list[Any]) -> AgentLLMResponse:
        llm_response = await self._llm_service.achat(
            messages=self._normalize_messages(messages),
            model=self._model,
            temperature=self._temperature,
        )
        return AgentLLMResponse(content=llm_response.content or "")

    async def astream(self, messages: list[Any]) -> AsyncIterator[AgentLLMStreamChunk]:
        response = await self.ainvoke(messages)
        if response.content:
            yield AgentLLMStreamChunk(content=response.content)


class LitigationLLMProvider:
    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm_service = llm_service

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    def create_llm(
        self,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AgentLLMAdapter:
        return AgentLLMAdapter(llm_service=self.llm_service, model=model, temperature=temperature)

    def create_llm_with_tools(
        self,
        tools: list[Any],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AgentLLMAdapter:
        llm = self.create_llm(model=model, temperature=temperature)
        return llm.bind_tools(tools) if tools else llm
