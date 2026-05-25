"""Prompt 模板同步服务。"""

from __future__ import annotations

from typing import Any

from django.db import transaction


def sync_prompt_templates(*, overwrite: bool = True) -> dict[str, int]:
    """将代码内置 Prompt 模板同步到数据库。"""
    from apps.core.llm.prompts import PromptManager
    from apps.core.models import PromptTemplate

    templates = list(PromptManager._templates.values())
    synced_count = 0
    with transaction.atomic():
        for item in templates:
            defaults = {
                "title": (item.description or item.name)[:200],
                "template": item.template,
                "description": item.description,
                "variables": item.variables,
                "category": (item.name.split("_", maxsplit=1)[0] or "general"),
                "is_active": True,
                "version": "1.0",
            }
            if overwrite:
                PromptTemplate.objects.update_or_create(name=item.name, defaults=defaults)
                synced_count += 1
                continue
            _, created = PromptTemplate.objects.get_or_create(name=item.name, defaults=defaults)
            if created:
                synced_count += 1
    return {"synced_count": synced_count}
