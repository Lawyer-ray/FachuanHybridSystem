"""Business logic services."""

from __future__ import annotations

"""
费用比对服务

本模块提供将PDF提取金额与系统计算金额进行比对的功能.

Requirements: 8.1-8.8
"""


import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from ..types import CaseComparisonInfo, CaseSearchResult, FeeComparisonResult

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, ILitigationFeeCalculatorService

logger = logging.getLogger("apps.fee_notice")


def _to_decimal(value: Any) -> Decimal | None:
    """将值转换为 Decimal"""
    return Decimal(str(value)) if value is not None else None


def _compare_single_fee(
    extracted: Decimal | None,
    calculated: Decimal | None,
    exact_threshold: Decimal,
    tolerance: Decimal,
    calculated_alt: Decimal | None = None,
) -> tuple[bool, bool, Decimal | None]:
    """比对单项费用,返回 (match, close, diff)"""
    if extracted is None or calculated is None:
        return False, False, None

    diff = abs(extracted - calculated)
    if calculated_alt is not None:
        diff_alt = abs(extracted - calculated_alt)
        diff = min(diff, diff_alt)

    if diff < exact_threshold:
        return True, False, Decimal("0")
    if diff <= tolerance:
        return False, True, diff
    return False, False, diff


class FeeComparisonService:
    """
    费用比对服务

    负责将PDF提取的费用金额与系统计算的金额进行比对.

    Requirements:
        - 8.1: 提供案件搜索下拉框,支持按案件名称或案号搜索
        - 8.2: 获取案件的案由ID和诉讼标的金额
        - 8.3: 调用 LitigationFeeCalculatorService 计算系统预期受理费
        - 8.4: 显示系统计算金额与PDF提取金额的比对结果
        - 8.5: 两个金额一致时显示"一致"状态
        - 8.6: 两个金额不一致时显示"不一致"状态并显示差异金额
        - 8.7: 同时显示:提取金额、计算金额、差异值
        - 8.8: 案件缺少案由或诉讼标的金额时返回提示信息
    """

    def __init__(
        self,
        case_service: ICaseService | None = None,
        fee_calculator_service: ILitigationFeeCalculatorService | None = None,
    ) -> None:
        """
        初始化费用比对服务

        Args:
            case_service: 案件服务(可选,支持依赖注入)
            fee_calculator_service: 费用计算服务(可选,支持依赖注入)
        """
        self._case_service = case_service
        self._fee_calculator_service = fee_calculator_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载案件服务"""
        if self._case_service is None:
            from apps.automation.services.wiring import get_case_service

            self._case_service = get_case_service()
        return self._case_service

    @property
    def fee_calculator_service(self) -> ILitigationFeeCalculatorService:
        """延迟加载费用计算服务"""
        if self._fee_calculator_service is None:
            from apps.automation.services.wiring import get_litigation_fee_calculator_service

            self._fee_calculator_service = get_litigation_fee_calculator_service()
        return self._fee_calculator_service

    def get_case_info_for_comparison(self, case_id: int) -> CaseComparisonInfo:
        """
        获取案件信息用于费用比对

        使用 ServiceLocator.get_case_service() 替代直接导入 Case 模型.

        Args:
            case_id: 案件ID

        Returns:
            CaseComparisonInfo: 案件信息(案由ID、诉讼标的金额等)

        Requirements: 8.2, 8.8, 5.1
        """
        # 使用 case_service 获取案件详细信息
        case_details = self.case_service.get_case_with_details_internal(case_id)

        if not case_details:
            logger.warning("案件不存在", extra={"case_id": case_id, "action": "get_case_info_for_comparison"})
            return CaseComparisonInfo(case_id=case_id, case_name="", is_complete=False, incomplete_reason="案件不存在")

        # 获取案号(取第一个案号)
        case_number = None
        case_numbers = case_details.get("case_numbers", [])
        if case_numbers:
            case_number = case_numbers[0].get("number")

        # 获取案由ID和名称
        cause_of_action_id = None
        cause_of_action_name = case_details.get("cause_of_action")

        # 尝试通过案由名称查找案由ID
        if cause_of_action_name:
            from apps.automation.services.wiring import get_cause_court_query_service

            cause_of_action_id = get_cause_court_query_service().get_cause_id_by_name_internal(cause_of_action_name)

        # 获取金额
        target_amount = case_details.get("target_amount")
        if target_amount is not None:
            target_amount = Decimal(str(target_amount))

        preservation_amount = case_details.get("preservation_amount")
        if preservation_amount is not None:
            preservation_amount = Decimal(str(preservation_amount))

        # 检查信息是否完整
        incomplete_reasons: list[Any] = []
        if not cause_of_action_id and not cause_of_action_name:
            incomplete_reasons.append("缺少案由")
        if target_amount is None or target_amount <= 0:
            incomplete_reasons.append("缺少诉讼标的金额")

        is_complete = len(incomplete_reasons) == 0
        incomplete_reason = "、".join(incomplete_reasons) if incomplete_reasons else None

        logger.info(
            "获取案件比对信息",
            extra={
                "case_id": case_id,
                "case_name": case_details.get("name"),
                "cause_of_action_id": cause_of_action_id,
                "target_amount": str(target_amount) if target_amount else None,
                "is_complete": is_complete,
            },
        )

        return CaseComparisonInfo(
            case_id=case_details.get("id") or case_id,
            case_name=case_details.get("name") or "",
            case_number=case_number,
            cause_of_action_id=cause_of_action_id,
            cause_of_action_name=cause_of_action_name,
            target_amount=target_amount,
            preservation_amount=preservation_amount,
            is_complete=is_complete,
            incomplete_reason=incomplete_reason,
        )

    def search_cases(self, keyword: str, limit: int = 20) -> list[CaseSearchResult]:
        """
        搜索案件(用于下拉框)

        支持按案件名称或案号搜索.
        使用 ServiceLocator.get_case_service() 替代直接导入 Case 模型.

        Args:
            keyword: 搜索关键词(案件名称或案号)
            limit: 返回数量限制

        Returns:
            List[CaseSearchResult]: 案件搜索结果列表

        Requirements: 8.1, 5.1
        """
        from decimal import Decimal

        if not keyword or not keyword.strip():
            return []

        keyword = keyword.strip()

        # 使用 case_service 搜索案件
        case_dtos = self.case_service.search_cases_internal(keyword, limit=limit)  # type: ignore

        case_ids: list[Any] = []
        case_number_map: dict[int, str | None] = {}
        if hasattr(self.case_service, "get_primary_case_numbers_by_case_ids_internal"):
            case_number_map = self.case_service.get_primary_case_numbers_by_case_ids_internal(case_ids)

        results: list[Any] = []
        for case_dto in case_dtos:
            case_number = case_number_map.get(cast(int, case_dto.id))

            # 转换 target_amount 为 Decimal
            target_amount = case_dto.target_amount
            if target_amount is not None and not isinstance(target_amount, Decimal):
                target_amount = Decimal(str(target_amount))

            results.append(
                CaseSearchResult(
                    id=cast(int, case_dto.id),
                    name=case_dto.name,
                    case_number=case_number,
                    cause_of_action=case_dto.cause_of_action,
                    target_amount=target_amount,
                )
            )

        logger.info(
            "搜索案件",
            extra={
                "keyword": keyword,
                "result_count": len(results),
                "action": "search_cases",
            },
        )

        return results

    def compare_fee(
        self,
        case_id: int,
        extracted_acceptance_fee: Decimal | None = None,
        extracted_preservation_fee: Decimal | None = None,
    ) -> FeeComparisonResult:
        """比对提取金额与系统计算金额"""
        TOLERANCE = Decimal("1.00")
        EXACT_THRESHOLD = Decimal("0.01")

        case_info = self.get_case_info_for_comparison(case_id)

        if not case_info.is_complete:
            return FeeComparisonResult(
                case_info=case_info,
                extracted_acceptance_fee=extracted_acceptance_fee,
                extracted_preservation_fee=extracted_preservation_fee,
                can_compare=False,
                message=f"无法计算预期费用:{case_info.incomplete_reason}",
            )

        calc_result = self.fee_calculator_service.calculate_all_fees(
            target_amount=case_info.target_amount,
            preservation_amount=case_info.preservation_amount,
            cause_of_action_id=case_info.cause_of_action_id,
        )

        calculated_acceptance_fee = _to_decimal(calc_result.get("acceptance_fee"))
        calculated_acceptance_fee_half = _to_decimal(calc_result.get("acceptance_fee_half"))
        calculated_preservation_fee = _to_decimal(calc_result.get("preservation_fee"))

        # 比对受理费(考虑全额和减半)
        acceptance_match, acceptance_close, acceptance_diff = _compare_single_fee(
            extracted_acceptance_fee,
            calculated_acceptance_fee,
            EXACT_THRESHOLD,
            TOLERANCE,
            calculated_acceptance_fee_half,
        )

        # 比对保全费
        preservation_match, preservation_close, preservation_diff = _compare_single_fee(
            extracted_preservation_fee,
            calculated_preservation_fee,
            EXACT_THRESHOLD,
            TOLERANCE,
        )

        result = FeeComparisonResult(
            case_info=case_info,
            extracted_acceptance_fee=extracted_acceptance_fee,
            extracted_preservation_fee=extracted_preservation_fee,
            calculated_acceptance_fee=calculated_acceptance_fee,
            calculated_acceptance_fee_half=calculated_acceptance_fee_half,
            calculated_preservation_fee=calculated_preservation_fee,
            acceptance_fee_match=acceptance_match,
            acceptance_fee_close=acceptance_close,
            acceptance_fee_diff=acceptance_diff,
            preservation_fee_match=preservation_match,
            preservation_fee_close=preservation_close,
            preservation_fee_diff=preservation_diff,
            can_compare=True,
            message=None,
        )

        logger.info(
            "费用比对完成",
            extra={
                "case_id": case_id,
                "acceptance_fee_match": acceptance_match,
                "acceptance_fee_close": acceptance_close,
                "action": "compare_fee",
            },
        )
        return result
