"""Module for template names presenter."""

from collections.abc import Iterable


def format_template_names(names: Iterable[str]) -> str:
    items = [n for n in names if n]
    if not items:
        return "无匹配模板"
    return "、".join(items)
