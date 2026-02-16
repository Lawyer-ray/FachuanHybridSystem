"""Business logic services."""

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderStats:
    placeholders_found: list[str]
    placeholders_hit: list[str]
    placeholders_missed: list[str]

    @property
    def hit_rate(self) -> float:
        total = len(self.placeholders_found)
        return (len(self.placeholders_hit) / total) if total else 1.0


class PlaceholderRenderService:
    _double_brace_pattern = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
    _single_brace_pattern = re.compile(r"(?<!\{)\{\s*([^{}]+?)\s*\}(?!\})")

    def render(
        self,
        template: str,
        variables: dict[str, Any],
        *,
        syntax: str = "single",
        keep_unmatched: bool = True,
    ) -> tuple[str, RenderStats]:
        if template is None:
            template = ""

        pattern = self._single_brace_pattern if syntax == "single" else self._double_brace_pattern

        found_keys = []
        hit_keys = []

        def repl(match: re.Match[str]) -> str:
            raw_key = match.group(1)
            key = raw_key.strip()
            found_keys.append(key)
            if key in variables:
                hit_keys.append(key)
                return str(variables.get(key, ""))
            return match.group(0) if keep_unmatched else ""

        rendered = pattern.sub(repl, template)
        found_unique = list(dict.fromkeys(found_keys))
        hit_unique = list(dict.fromkeys(hit_keys))
        missed_unique = [k for k in found_unique if k not in set(hit_unique)]
        return rendered, RenderStats(found_unique, hit_unique, missed_unique)
