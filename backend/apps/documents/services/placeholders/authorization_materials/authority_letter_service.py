"""Business logic services."""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class AuthorityLetterPlaceholderService(BasePlaceholderService):
    name: str = "authority_letter_placeholder_service"
    display_name: str = "授权委托材料-所函"
    description: str = "生成所函所需占位符"
    category: str = "authorization_material"
    placeholder_keys: ClassVar = ["当前阶段", "律师姓名及联系方式"]
    placeholder_metadata: ClassVar = {
        "当前阶段": {
            "display_name": "当前阶段",
            "description": "案件的当前阶段(显示值)",
            "example_value": "一审",
        },
        "律师姓名及联系方式": {
            "display_name": "律师姓名及联系方式",
            "description": "主办律师在前,其余在后:AA律师:136...;BB律师:123....",
            "example_value": "张三律师:13678789505;李四律师:123849506.",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case = context_data.get("case")
        if not case:
            return {
                "当前阶段": "",
                "律师姓名及联系方式": "",
            }

        stage_display = ""
        if getattr(case, "current_stage", None):
            stage_display = getattr(case, "get_current_stage_display", lambda: "")() or ""

        contact_text = self._format_lawyers_contact(case)

        return {
            "当前阶段": stage_display,
            "律师姓名及联系方式": contact_text,
        }

    def _format_lawyers_contact(self, case: Any) -> str:
        try:
            assignments = list(case.assignments.select_related("lawyer").order_by("id"))
        except Exception as e:
            logger.warning(
                "获取案件律师列表失败",
                extra={"case_id": getattr(case, "id", None), "error": str(e)},
            )
            assignments: list[Any] = []

        parts: list[str] = []
        for assignment in assignments:
            lawyer = getattr(assignment, "lawyer", None)
            if not lawyer:
                continue
            name = getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or ""
            if not name:
                continue
            if not name.endswith("律师"):
                name = f"{name}律师"
            contact = getattr(lawyer, "phone", None) or ""
            if contact:
                parts.append(f"{name}:{contact}")
            else:
                parts.append(name)

        if not parts:
            return ""

        text = ";".join(parts)
        if not text.endswith("."):
            text += "."
        return text
