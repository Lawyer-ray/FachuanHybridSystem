"""Business logic services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class TemplateBindingAssemblerConfig:
    sub_type_display: dict[str, str]


class TemplateBindingAssembler:
    def __init__(self, config: TemplateBindingAssemblerConfig | None = None) -> None:
        self._config = config or TemplateBindingAssemblerConfig(sub_type_display={})

    def binding_to_dict(self, *, binding: Any, template: Any) -> dict[str, Any]:
        return {
            "binding_id": binding.id,
            "template_id": binding.template_id,
            "name": getattr(template, "name", "") if template else "",
            "description": (getattr(template, "description", "") or "") if template else "",
            "binding_source": binding.binding_source,
            "binding_source_display": str(binding.get_binding_source_display()),
            "created_at": binding.created_at.isoformat() if getattr(binding, "created_at", None) else None,
        }

    def general_to_dict(self, *, template: Any) -> dict[str, Any]:
        return {
            "binding_id": None,
            "template_id": template.id,
            "name": getattr(template, "name", "") or "",
            "description": getattr(template, "description", "") or "",
            "binding_source": "general",
            "binding_source_display": str(_("通用")),
            "created_at": None,
        }

    def available_to_dict(self, *, template: Any) -> dict[str, Any]:
        sub_type = cast(str | None, getattr(template, "case_sub_type", None))
        sub_type_key = sub_type or ""
        return {
            "template_id": template.id,
            "name": getattr(template, "name", "") or "",
            "case_sub_type": sub_type,
            "case_sub_type_display": self._config.sub_type_display.get(sub_type_key, sub_type_key),
        }

    def categories_response(self, *, grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        categories: list[dict[str, Any]] = []
        for category, templates in grouped.items():
            categories.append(
                {
                    "category": category,
                    "category_display": self._config.sub_type_display.get(category, category),
                    "templates": templates,
                }
            )
        return {"categories": categories, "total_count": sum(len(cat["templates"]) for cat in categories)}

    def unified_templates(self, *, items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(items)
