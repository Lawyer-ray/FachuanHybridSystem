"""Tests for unified placeholder fallback slash rules."""

from __future__ import annotations

from apps.documents.services.generation.prompts import PromptSpec
from apps.documents.services.placeholders.fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    build_docx_render_context,
    resolve_render_variable,
)
from apps.litigation_ai.services.placeholder_render_service import PlaceholderRenderService


class _DocStub:
    def get_undeclared_template_variables(self, context: dict[str, object] | None = None) -> set[str]:
        if context and "known" in context:
            return {"missing_key"}
        return set()


def test_build_docx_render_context_fills_undeclared_with_slash() -> None:
    context = build_docx_render_context(doc=_DocStub(), context={"known": "ok"})

    assert context["known"] == "ok"
    assert context["missing_key"] == PLACEHOLDER_FALLBACK_VALUE


def test_resolve_render_variable_returns_slash_for_none_and_missing() -> None:
    hit, value = resolve_render_variable({"a": None}, "a")
    assert hit is False
    assert value == PLACEHOLDER_FALLBACK_VALUE

    hit_missing, value_missing = resolve_render_variable({}, "missing")
    assert hit_missing is False
    assert value_missing == PLACEHOLDER_FALLBACK_VALUE


def test_placeholder_render_service_renders_slash_for_missing_and_none() -> None:
    rendered, stats = PlaceholderRenderService().render(
        "姓名:{name};地址:{address}",
        {"name": None},
        syntax="single",
        keep_unmatched=True,
    )

    assert rendered == f"姓名:{PLACEHOLDER_FALLBACK_VALUE};地址:{PLACEHOLDER_FALLBACK_VALUE}"
    assert stats.placeholders_found == ["name", "address"]
    assert stats.placeholders_hit == []
    assert stats.placeholders_missed == ["name", "address"]


def test_prompt_spec_render_user_message_uses_slash_for_none_and_missing() -> None:
    prompt = PromptSpec(system_prompt="s", user_template="A:{a};B:{b}", format_instructions="")

    rendered = prompt.render_user_message({"a": None})

    assert rendered == f"A:{PLACEHOLDER_FALLBACK_VALUE};B:{PLACEHOLDER_FALLBACK_VALUE}"
