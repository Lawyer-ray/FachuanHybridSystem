"""Prompt templates for litigation document generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.core.llm.structured_output import json_schema_instructions

logger = logging.getLogger("apps.documents.generation")


class _SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


@dataclass(frozen=True)
class PromptSpec:
    system_prompt: str
    user_template: str
    format_instructions: str

    def render_user_message(self, values: dict[str, Any]) -> str:
        normalized: dict[str, str] = {
            key: "" if value is None else str(value)
            for key, value in (values or {}).items()
        }
        normalized.setdefault("format_instructions", self.format_instructions)
        return self.user_template.format_map(_SafeDict(normalized))


class PromptTemplateFactory:
    """Prompt template factory."""

    def get_complaint_prompt(self) -> PromptSpec:
        from .outputs import ComplaintOutput

        format_instructions = json_schema_instructions(ComplaintOutput)
        db_template = self._load_from_database("complaint")
        if db_template:
            logger.info("使用数据库中的起诉状 Prompt 模板")
            return PromptSpec(
                system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.",
                user_template=db_template,
                format_instructions=format_instructions,
            )

        logger.warning("Prompt 版本不存在,使用默认起诉状模板", extra={"prompt_name": "complaint"})
        return PromptSpec(
            system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.请根据提供的信息生成规范的起诉状.",
            user_template="""请根据以下信息生成起诉状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
诉讼请求:{litigation_request}
事实与理由:{facts_and_reasons}

{format_instructions}
""",
            format_instructions=format_instructions,
        )

    def get_defense_prompt(self) -> PromptSpec:
        from .outputs import DefenseOutput

        format_instructions = json_schema_instructions(DefenseOutput)
        db_template = self._load_from_database("defense")
        if db_template:
            logger.info("使用数据库中的答辩状 Prompt 模板")
            return PromptSpec(
                system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.",
                user_template=db_template,
                format_instructions=format_instructions,
            )

        logger.warning("Prompt 版本不存在,使用默认答辩状模板", extra={"prompt_name": "defense"})
        return PromptSpec(
            system_prompt="你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.请根据提供的信息生成规范的答辩状.",
            user_template="""请根据以下信息生成答辩状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
答辩意见:{defense_opinion}
答辩理由:{defense_reasons}

{format_instructions}
""",
            format_instructions=format_instructions,
        )

    def _load_from_database(self, name: str) -> Any:
        try:
            from apps.documents.services.prompt_version_service import PromptVersionService

            service = PromptVersionService()
            return service.get_active_template(name)
        except ImportError:
            logger.debug("PromptVersionService 未实现,使用默认模板")
            return None
        except Exception:
            logger.exception("load_prompt_from_database_failed", extra={"prompt_name": name})
            raise
