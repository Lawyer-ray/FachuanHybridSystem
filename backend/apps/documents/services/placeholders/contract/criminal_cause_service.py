"""
刑事案由占位符服务

从合同绑定的案件中提取案由(罪名).
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class CriminalCauseService(BasePlaceholderService):
    """刑事案由服务"""

    name: str = "criminal_cause_service"
    display_name: str = "刑事案由服务"
    description: str = "从合同绑定的案件中提取案由(罪名),去除编号后缀"
    category: str = "contract"
    placeholder_keys: ClassVar = ["案由"]
    placeholder_metadata: ClassVar = {
        "案由": {
            "display_name": "案由",
            "description": "合同绑定案件的案由/罪名,自动去除编号后缀",
            "example_value": "危险作业罪",
        }
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成案由占位符

        Args:
            context_data: 包含 contract 的上下文字典

        Returns:
            {"案由": "清理后的案由字符串"}
        """
        try:
            case = context_data.get("case")
            if case:
                return {"案由": self._clean_cause_of_action(case)}

            case_dto = context_data.get("case_dto")
            dto_cause = getattr(case_dto, "cause_of_action", None)
            if dto_cause:
                return {"案由": str(dto_cause).strip()}

            contract = context_data.get("contract")
            if not contract:
                logger.warning("合同对象为空，且未提供案件对象")
                return {"案由": ""}

            result = self._extract_cause_of_action(contract)
            return {"案由": result}

        except Exception as e:
            logger.warning(
                "生成案由占位符失败: %s",
                e,
                extra={"contract_id": getattr(context_data.get("contract"), "id", None)},
                exc_info=True,
            )
            return {"案由": ""}

    def _extract_cause_of_action(self, contract: Any) -> str:
        """
        从合同绑定的案件中提取案由

        Args:
            contract: Contract 实例

        Returns:
            清理后的案由字符串
        """
        try:
            # 获取合同绑定的案件
            cases = list(contract.cases.all())

            if not cases:
                return ""

            # 获取第一个案件的案由(通常一个合同只绑定一个案件)
            causes: list[Any] = []
            for case in cases:
                cause = self._clean_cause_of_action(case)
                if cause and cause not in causes:
                    causes.append(cause)

            # 如果有多个案由,用顿号分隔
            return "、".join(causes)

        except AttributeError:
            logger.warning("合同对象没有 cases 属性", extra={"contract_id": getattr(contract, "id", None)})
            return ""
        except Exception as e:
            logger.warning("提取案由失败: %s", e, extra={"contract_id": getattr(contract, "id", None)})
            return ""

    def _clean_cause_of_action(self, case: Any) -> Any:
        """
        清理案由,直接返回案件“案由”字段值

        Args:
            case: Case 实例

        Returns:
            清理后的案由字符串
        """
        try:
            cause = getattr(case, "cause_of_action", None)
            if not cause:
                return ""
            return str(cause).strip()

        except Exception as e:
            logger.warning("清理案由失败: %s", e, extra={"case_id": getattr(case, "id", None)})
            return ""
