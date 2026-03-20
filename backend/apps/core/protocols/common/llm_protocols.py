"""Module for llm protocols."""

from typing import Any, Protocol


class ILLMService(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> Any: ...

    async def achat(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> Any: ...

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> Any: ...


class IPromptVersionService(Protocol):
    def get_active_prompt_template(self, name: str) -> str | None: ...

    def get_prompt_template_internal(self, name: str) -> str | None: ...
