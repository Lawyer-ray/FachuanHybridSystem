"""
代理阶段占位符服务

格式化代理阶段信息.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class RepresentationStageService(BasePlaceholderService):
    """代理阶段服务"""

    name: str = "representation_stage_service"
    display_name: str = "代理阶段服务"
    description: str = "格式化代理阶段,第二个及以后加(如有)"
    category: str = "contract"
    placeholder_keys: ClassVar = ["代理阶段"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成代理阶段占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含代理阶段占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{代理阶段}} - 代理阶段,顿号分隔
            result["代理阶段"] = self.format_stages(contract)

        return result

    def format_stages(self, contract: Any) -> str:
        """
        格式化代理阶段(第二个及以后加"如有")

        Args:
            contract: Contract 实例

        Returns:
            格式化的代理阶段字符串
        """
        try:
            from apps.core.enums import CaseStage

            stages = getattr(contract, "representation_stages", None) or []

            if not stages:
                return ""

            # 将阶段代码转换为显示名称
            stage_choices = dict(CaseStage.choices)
            stage_names = [str(stage_choices.get(s, s)) for s in stages]

            # 如果有2个及以上的代理阶段,在后面的阶段中加入(如有)
            if len(stage_names) >= 2:
                formatted_stages = [stage_names[0]]  # 第一个阶段不加(如有)
                for stage in stage_names[1:]:
                    formatted_stages.append(f"{stage}(如有)")
                return "、".join(formatted_stages)
            else:
                return "、".join(stage_names)

        except Exception as e:
            logger.warning(f"格式化代理阶段失败: {e}", extra={"contract_id": getattr(contract, "id", None)})
            return ""
