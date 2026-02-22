"""
律师信息占位符服务

提供律师信息格式化功能.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class LawyerInfoService(BasePlaceholderService):
    """律师信息服务"""

    name: str = "lawyer_info_service"
    display_name: str = "律师信息服务"
    description: str = "格式化律师姓名,主办在前"
    category: str = "lawyer"
    placeholder_keys: ClassVar = ["律师姓名", "主办律师", "协办律师"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成律师占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含律师占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            assignments = self._get_lawyer_assignments(contract)

            # {{律师姓名}} - 律师姓名,主办在前,顿号分隔
            result["律师姓名"] = self.format_lawyer_names(assignments)

            # {{主办律师}} - 主办律师姓名
            result["主办律师"] = self._get_primary_lawyer_name(assignments)

            # {{协办律师}} - 协办律师姓名,顿号分隔
            result["协办律师"] = self._get_assistant_lawyer_names(assignments)

        return result

    def _get_lawyer_assignments(self, contract: Any) -> list[Any]:
        """
        获取合同中的律师分配列表

        Args:
            contract: Contract 实例

        Returns:
            律师分配列表
        """
        try:
            assignments: list[Any] = []
            for assignment in contract.assignments.all():
                assignments.append(assignment)
            return assignments
        except Exception:
            logger.exception("get_lawyer_assignments_failed", extra={"contract_id": getattr(contract, "id", None)})
            raise

    def format_lawyer_names(self, assignments: list[Any]) -> str:
        """
        格式化律师姓名(主办在前,顿号分隔)

        Args:
            assignments: 律师分配列表

        Returns:
            格式化的律师姓名字符串
        """
        if not assignments:
            logger.info("律师分配列表为空")
            return ""

        logger.info("开始格式化律师姓名,共 %s 个律师分配", len(assignments))

        primary_lawyers: list[Any] = []
        assistant_lawyers: list[Any] = []

        # 分离主办和协办律师
        for assignment in assignments:
            lawyer_name = self._get_lawyer_name(assignment)
            is_primary = hasattr(assignment, "is_primary") and assignment.is_primary

            logger.info(
                f"处理律师分配 - ID: {getattr(assignment, 'id', 'N/A')}, "
                f"姓名: {lawyer_name or '(空)'}, "
                f"是否主办: {is_primary}"
            )

            if lawyer_name:
                if is_primary:
                    primary_lawyers.append(lawyer_name)
                else:
                    assistant_lawyers.append(lawyer_name)
            else:
                logger.warning(
                    f"律师姓名为空 - 分配ID: {getattr(assignment, 'id', 'N/A')}, "
                    f"律师ID: {getattr(getattr(assignment, 'lawyer', None), 'id', 'N/A')}"
                )

        # 主办律师在前,协办律师在后
        all_lawyers = primary_lawyers + assistant_lawyers

        result = "、".join(all_lawyers)
        logger.info("格式化完成,结果: %s", result)

        return result

    def _get_primary_lawyer_name(self, assignments: list[Any]) -> str:
        """
        获取主办律师姓名

        Args:
            assignments: 律师分配列表

        Returns:
            主办律师姓名
        """
        for assignment in assignments:
            if hasattr(assignment, "is_primary") and assignment.is_primary:
                return self._get_lawyer_name(assignment)

        # 如果没有主办律师,返回第一个律师
        if assignments:
            return self._get_lawyer_name(assignments[0])

        return ""

    def _get_assistant_lawyer_names(self, assignments: list[Any]) -> str:
        """
        获取协办律师姓名(顿号分隔)

        Args:
            assignments: 律师分配列表

        Returns:
            协办律师姓名字符串
        """
        assistant_lawyers: list[Any] = []

        for assignment in assignments:
            if not (hasattr(assignment, "is_primary") and assignment.is_primary):
                lawyer_name = self._get_lawyer_name(assignment)
                if lawyer_name:
                    assistant_lawyers.append(lawyer_name)

        return "、".join(assistant_lawyers)

    def _get_lawyer_name(self, assignment: Any) -> str:
        """
        从律师分配中获取律师姓名

        Args:
            assignment: 律师分配实例

        Returns:
            律师姓名(优先使用 real_name,否则使用 username)
        """
        try:
            if hasattr(assignment, "lawyer") and assignment.lawyer:
                lawyer = assignment.lawyer
                # 优先使用真实姓名,否则使用用户名
                real_name = getattr(lawyer, "real_name", None)
                username = getattr(lawyer, "username", "")

                # 处理 real_name 为空字符串的情况
                result = (real_name and real_name.strip()) or (username and username.strip()) or ""

                if not result:
                    logger.warning(
                        f"律师姓名为空 - 律师ID: {getattr(lawyer, 'id', 'N/A')}, "
                        f"real_name: '{real_name}', username: '{username}'"
                    )

                return result
            else:
                logger.warning(
                    f"律师对象不存在 - 分配ID: {getattr(assignment, 'id', 'N/A')}, "
                    f"hasattr(lawyer): {hasattr(assignment, 'lawyer')}, "
                    f"lawyer: {getattr(assignment, 'lawyer', None)}"
                )
        except Exception as e:
            logger.warning(
                f"获取律师姓名失败: {e}", extra={"assignment_id": getattr(assignment, "id", None)}, exc_info=True
            )

        return ""
