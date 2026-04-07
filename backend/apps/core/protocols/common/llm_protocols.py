"""Module for llm protocols."""

from collections.abc import AsyncIterator, Iterator
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

    def stream(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> Iterator[Any]: ...

    async def astream(
        self,
        messages: list[dict[str, str]],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[Any]: ...

    def embed_texts(
        self,
        texts: list[str],
        backend: str | None = None,
        model: str | None = None,
        fallback: bool = True,
        **kwargs: Any,
    ) -> list[list[float]]: ...
