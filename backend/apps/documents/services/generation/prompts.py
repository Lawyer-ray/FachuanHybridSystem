"""Prompt templates for litigation document generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions
from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE

logger = logging.getLogger("apps.documents.generation")


class _SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return PLACEHOLDER_FALLBACK_VALUE


@dataclass(frozen=True)
class PromptSpec:
    system_prompt: str
    user_template: str
    format_instructions: str

    def render_user_message(self, values: dict[str, Any]) -> str:
        normalized: dict[str, str] = {
            key: PLACEHOLDER_FALLBACK_VALUE if value is None else str(value) for key, value in (values or {}).items()
        }
        normalized.setdefault("format_instructions", self.format_instructions)
        return self.user_template.format_map(_SafeDict(normalized))


# Hardcoded prompt specs for litigation documents
COMPLAINT_PROMPT = PromptSpec(
    system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.",
    user_template="""请根据以下信息生成起诉状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
诉讼请求:{litigation_request}
事实与理由:{facts_and_reasons}

{format_instructions}
""",
    format_instructions="",
)

DEFENSE_PROMPT = PromptSpec(
    system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.",
    user_template="""请根据以下信息生成答辩状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
答辩意见:{defense_opinion}
答辩理由:{defense_reasons}

{format_instructions}
""",
    format_instructions="",
)


def get_complaint_prompt() -> PromptSpec:
    """Get the complaint prompt spec."""
    from .outputs import ComplaintOutput

    format_instructions = json_schema_instructions(ComplaintOutput)
    prompt = COMPLAINT_PROMPT
    return PromptSpec(
        system_prompt=prompt.system_prompt,
        user_template=prompt.user_template,
        format_instructions=format_instructions,
    )


def get_defense_prompt() -> PromptSpec:
    """Get the defense prompt spec."""
    from .outputs import DefenseOutput

    format_instructions = json_schema_instructions(DefenseOutput)
    prompt = DEFENSE_PROMPT
    return PromptSpec(
        system_prompt=prompt.system_prompt,
        user_template=prompt.user_template,
        format_instructions=format_instructions,
    )
