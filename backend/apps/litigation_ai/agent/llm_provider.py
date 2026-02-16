"""Module for llm provider."""

from typing import Any

from apps.litigation_ai.services.wiring import get_llm_service


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
    ) -> Any:
        return self.llm_service.get_langchain_llm(model=model, temperature=temperature)

    def create_llm_with_tools(
        self,
        tools: list[Any],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> Any:
        llm = self.create_llm(model=model, temperature=temperature)
        return llm.bind_tools(tools) if tools else llm
