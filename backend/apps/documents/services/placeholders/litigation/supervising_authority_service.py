"""
审理机构服务

Requirements: 3.1, 3.2, 3.3, 3.4, 8.3
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class SupervisingAuthorityService(BasePlaceholderService):
    """审理机构服务"""

    name: str = "litigation_supervising_authority_service"
    display_name: str = "诉讼文书-审理机构"
    description: str = "生成诉讼文书模板中的审理机构占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.COURT]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.COURT: self.get_supervising_authority(case_id)}

    def get_supervising_authority(self, case_id: int) -> Any:
        """
        获取审理机构名称

        Args:
            case_id: 案件 ID

        Returns:
            str: 审理机构名称,如果没有找到则返回空字符串

        Requirements: 3.1, 3.2, 3.3, 3.4, 8.3
        """
        from apps.core.enums import AuthorityType

        case_details = self.case_details_accessor.require_case_details(case_id=case_id)

        try:
            # 从 case_details 中获取主管机关列表
            supervising_authorities = case_details.get("supervising_authorities", [])

            # 筛选 authority_type == "审理机构"
            for authority in supervising_authorities:
                if authority.get("authority_type") == AuthorityType.TRIAL:
                    name = authority.get("name")
                    if name:
                        logger.info(f"找到审理机构: {name}")
                        return name

            logger.warning(f"未找到审理机构: case_id={case_id}")
            return ""

        except Exception as e:
            logger.error(f"查询审理机构失败: {e!s}", exc_info=True)
            return ""
