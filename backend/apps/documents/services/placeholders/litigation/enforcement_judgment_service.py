"""强制执行申请书 - 执行依据主文占位符服务"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementJudgmentMainTextService(BasePlaceholderService):
    """执行依据主文服务"""

    name: str = "enforcement_judgment_main_text_service"
    display_name: str = "诉讼文书-强制执行申请书执行依据主文"
    description: str = "生成强制执行申请书模板中的执行依据主文占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_JUDGMENT_MAIN_TEXT]

    def __init__(self) -> None:
        from apps.documents.services.placeholders.litigation.case_details_accessor import (
            LitigationCaseDetailsAccessor,
        )

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def get_judgment_main_text(self, case_id: int) -> str:
        """
        获取执行依据主文（从案号的 document_content 字段提取）

        Args:
            case_id: 案件 ID

        Returns:
            执行依据主文内容
        """
        case_details = self.case_details_accessor.require_case_details(case_id=case_id)
        case_numbers = case_details.get("case_numbers", []) or []

        # 优先取生效的案号
        for cn in case_numbers:
            if cn.get("is_active"):
                content = cn.get("document_content")
                if content:
                    logger.info("获取生效案号执行依据主文: case_id=%s, length=%d", case_id, len(content))
                    return content

        # 没有生效的案号则按顺序拼接所有有内容的案号（如一审+二审）
        all_contents: list[str] = []
        for cn in case_numbers:
            content = cn.get("document_content")
            if content:
                all_contents.append(content)

        if all_contents:
            combined = "\n".join(all_contents)
            logger.info("获取案号执行依据主文（多份）: case_id=%s, 份数=%d, 总长度=%d", case_id, len(all_contents), len(combined))
            return combined

        logger.warning("未找到执行依据主文: case_id=%s", case_id)
        return ""

    def generate(self, context: dict) -> dict:
        """
        生成执行依据主文占位符

        Args:
            context: 包含 case_id 和 case_dto 的上下文

        Returns:
            占位符字典
        """
        case_id = context.get("case_id")
        if not case_id:
            return {LitigationPlaceholderKeys.ENFORCEMENT_JUDGMENT_MAIN_TEXT: ""}

        judgment_main_text = self.get_judgment_main_text(case_id)
        return {LitigationPlaceholderKeys.ENFORCEMENT_JUDGMENT_MAIN_TEXT: judgment_main_text}