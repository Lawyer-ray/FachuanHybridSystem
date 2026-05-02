"""Business logic services."""

from typing import Any


class PromptTemplateService:
    def get_system_template(self, name: str) -> str | None:
        from ..wiring import get_prompt_version_service  # type: ignore[attr-defined]

        return get_prompt_version_service().get_active_prompt_template(name)  # type: ignore[no-any-return]

    def replace_variables(self, template: str, variables: dict[str, Any]) -> str:
        from .placeholder_render_service import PlaceholderRenderService

        rendered, _stats = PlaceholderRenderService().render(template, variables, syntax="single", keep_unmatched=True)
        return rendered
