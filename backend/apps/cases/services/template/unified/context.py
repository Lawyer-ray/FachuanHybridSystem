"""Business logic services."""

from __future__ import annotations

from typing import Any


class TemplateContextBuilder:
    def __init__(self, *, enhanced_builder: Any | None = None) -> None:
        self._enhanced_builder = enhanced_builder

    @property
    def enhanced_builder(self) -> Any:
        if self._enhanced_builder is None:
            from apps.cases.dependencies import get_enhanced_context_builder

            self._enhanced_builder = get_enhanced_context_builder()
        return self._enhanced_builder

    def build(self, *, case: Any, client: Any | None = None, clients: list[Any] | None = None) -> dict[str, Any]:
        context_data: dict[str, Any] = {"case": case}
        if client:
            context_data["client"] = client
        if clients:
            context_data["clients"] = clients
        return self.enhanced_builder.build_context(context_data)  # type: ignore[no-any-return]
