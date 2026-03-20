"""
强制执行申请书基础字段服务

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 8.3, 9.1, 9.2
"""

import logging
from decimal import Decimal
from typing import Any, ClassVar

from django.utils import timezone

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementCaseNumberService(BasePlaceholderService):
    """强制执行申请书执行依据案号服务"""

    name: str = "enforcement_case_number_service"
    display_name: str = "诉讼文书-强制执行申请书执行依据案号"
    description: str = "生成强制执行申请书模板中的执行依据案号占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_CASE_NUMBER]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_CASE_NUMBER: self.get_case_number(case_id)}

    def get_case_number(self, case_id: int) -> str:
        """
        获取执行依据案号（取生效的案号，拼接文书名称）

        Args:
            case_id: 案件 ID

        Returns:
            str: 执行依据案号，如 (2025)粤0606民初38361号《民事调解书》
        """
        case_details = self.case_details_accessor.require_case_details(case_id=case_id)
        case_numbers = case_details.get("case_numbers", []) or []

        def build_full_number(cn: dict) -> str:
            """构建完整案号"""
            number = cn.get("number", "") or ""
            document_name = cn.get("document_name")
            if document_name:
                # 如果 document_name 已包含书名号《》，直接拼接
                if document_name.startswith("《"):
                    return f"{number}{document_name}"
                return f"{number}《{document_name}》"
            return number

        # 优先取生效的案号
        for cn in case_numbers:
            if cn.get("is_active"):
                full_number = build_full_number(cn)
                logger.info("获取到生效案号: case_id=%s, number=%s", case_id, full_number)
                return full_number

        # 没有生效的案号则取第一个
        if case_numbers:
            full_number = build_full_number(case_numbers[0])
            logger.info("未找到生效案号，使用第一个: case_id=%s, number=%s", case_id, full_number)
            return full_number

        logger.warning("未找到案号信息: case_id=%s", case_id)
        return ""


@PlaceholderRegistry.register
class EnforcementCourtService(BasePlaceholderService):
    """强制执行申请书管辖法院服务"""

    name: str = "enforcement_court_service"
    display_name: str = "诉讼文书-强制执行申请书管辖法院"
    description: str = "生成强制执行申请书模板中的管辖法院占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_COURT]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_COURT: self.get_court(case_id)}

    def get_court(self, case_id: int) -> str:
        """
        获取管辖法院名称

        Args:
            case_id: 案件 ID

        Returns:
            str: 管辖法院名称
        """
        case_details = self.case_details_accessor.require_case_details(case_id=case_id)
        supervising_authorities = case_details.get("supervising_authorities", []) or []

        for authority in supervising_authorities:
            name = authority.get("name", "").strip()
            if name:
                logger.info("获取到管辖法院: case_id=%s, name=%s", case_id, name)
                return name

        logger.warning("未找到管辖法院信息: case_id=%s", case_id)
        return ""


@PlaceholderRegistry.register
class EnforcementEffectiveDateService(BasePlaceholderService):
    """强制执行申请书判决生效日期服务"""

    name: str = "enforcement_effective_date_service"
    display_name: str = "诉讼文书-强制执行申请书判决生效日期"
    description: str = "生成强制执行申请书模板中的判决生效日期占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_EFFECTIVE_DATE]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_EFFECTIVE_DATE: self.get_effective_date(case_id)}

    def get_effective_date(self, case_id: int) -> str:
        """
        获取判决生效日期

        Args:
            case_id: 案件 ID

        Returns:
            str: 判决生效日期（格式：YYYY年MM月DD日）
        """
        case_details = self.case_details_accessor.require_case_details(case_id=case_id)
        effective_date = self.case_details_accessor._coerce_date(case_details.get("effective_date"))

        if effective_date:
            formatted = effective_date.strftime("%Y年%m月%d日")
            logger.info("获取到判决生效日期: case_id=%s, date=%s", case_id, formatted)
            return formatted

        logger.warning("未找到判决生效日期: case_id=%s", case_id)
        return ""


@PlaceholderRegistry.register
class EnforcementTargetAmountService(BasePlaceholderService):
    """强制执行申请书涉案金额服务"""

    name: str = "enforcement_target_amount_service"
    display_name: str = "诉讼文书-强制执行申请书涉案金额"
    description: str = "生成强制执行申请书模板中的涉案金额占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_TARGET_AMOUNT]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_TARGET_AMOUNT: self.get_target_amount(case_id)}

    def get_target_amount(self, case_id: int) -> str:
        """
        获取涉案金额

        Args:
            case_id: 案件 ID

        Returns:
            str: 涉案金额（格式：XXX元整）
        """
        case_details = self.case_details_accessor.require_case_details(case_id=case_id)
        target_amount = case_details.get("target_amount")

        if target_amount is not None:
            # 转换为 Decimal 处理
            amount = Decimal(str(target_amount))
            formatted = f"{amount.quantize(Decimal('0.01'))}元"
            logger.info("获取到涉案金额: case_id=%s, amount=%s", case_id, formatted)
            return formatted

        logger.warning("未找到涉案金额: case_id=%s", case_id)
        return ""


@PlaceholderRegistry.register
class EnforcementCauseOfActionService(BasePlaceholderService):
    """强制执行申请书案由服务"""

    name: str = "enforcement_cause_of_action_service"
    display_name: str = "诉讼文书-强制执行申请书案由"
    description: str = "生成强制执行申请书模板中的案由占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.CAUSE_OF_ACTION]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_dto = context_data.get("case_dto")
        cause_of_action = getattr(case_dto, "cause_of_action", None) or "民事纠纷"
        return {LitigationPlaceholderKeys.CAUSE_OF_ACTION: cause_of_action}
