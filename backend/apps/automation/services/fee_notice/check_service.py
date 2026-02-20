"""Business logic services."""

from __future__ import annotations

"""
交费通知书检查服务

本模块提供在法院短信处理流程中检查交费通知书并比对费用的功能.
在案件绑定完成后、飞书通知发送前触发检查.
"""


import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

    from .comparison_service import CaseComparisonInfo, FeeComparisonService # type: ignore
    from .extraction_service import FeeNoticeExtractionService

logger = logging.getLogger("apps.automation")


@dataclass
class FeeCheckItem:
    """单个费用检查项"""

    file_name: str  # 文件名
    file_path: str  # 文件路径
    # 提取的费用
    extracted_acceptance_fee: Decimal | None = None
    extracted_preservation_fee: Decimal | None = None
    # 计算的费用
    calculated_acceptance_fee: Decimal | None = None
    calculated_acceptance_fee_half: Decimal | None = None
    calculated_preservation_fee: Decimal | None = None
    # 比对结果
    acceptance_fee_match: bool = False
    acceptance_fee_close: bool = False  # 视为一致(差异在1元内)
    acceptance_fee_diff: Decimal | None = None
    preservation_fee_match: bool = False
    preservation_fee_close: bool = False
    preservation_fee_diff: Decimal | None = None
    # 是否可比对
    can_compare: bool = True
    compare_message: str | None = None  # 无法比对的原因


@dataclass
class FeeCheckResult:
    """费用检查结果"""

    has_fee_notice: bool = False  # 是否有交费通知书
    items: list[FeeCheckItem] = field(default_factory=list)  # 检查项列表
    case_name: str | None = None
    case_number: str | None = None
    cause_of_action: str | None = None
    target_amount: Decimal | None = None


class FeeNoticeCheckService:
    """
    交费通知书检查服务

    在法院短信处理流程中检查PDF是否包含交费通知书,
    如果有则提取费用并与系统计算的费用进行比对.
    """

    # 交费通知书关键词(支持多种表述方式)
    FEE_NOTICE_KEYWORDS: ClassVar = [
        "交费通知书",
        "缴费通知书",
        "交纳诉讼费用通知书",
        "缴纳诉讼费用通知书",
        "诉讼费用通知书",
        "费用通知书",
    ]

    def __init__(
        self,
        extraction_service: FeeNoticeExtractionService | None = None,
        comparison_service: FeeComparisonService | None = None,
    ) -> None:
        """
        初始化服务

        Args:
            extraction_service: 费用提取服务(可选,支持依赖注入)
            comparison_service: 费用比对服务(可选,支持依赖注入)
        """
        self._extraction_service = extraction_service
        self._comparison_service = comparison_service

    @property
    def extraction_service(self) -> FeeNoticeExtractionService:
        """延迟加载费用提取服务"""
        if self._extraction_service is None:
            from .extraction_service import FeeNoticeExtractionService

            self._extraction_service = FeeNoticeExtractionService()
        return self._extraction_service

    @property
    def comparison_service(self) -> FeeComparisonService:
        """延迟加载费用比对服务"""
        if self._comparison_service is None:
            from .comparison_service import FeeComparisonService

            self._comparison_service = FeeComparisonService()
        return self._comparison_service

    def check_fee_notices(
        self,
        sms: CourtSMS,
        document_paths: list[str],
    ) -> FeeCheckResult:
        """
        检查文书中的交费通知书并比对费用

        Args:
            sms: 法院短信记录(必须已绑定案件)
            document_paths: 文书文件路径列表

        Returns:
            FeeCheckResult: 检查结果
        """
        result = FeeCheckResult()

        if not sms.case:
            logger.warning(f"短信未绑定案件,跳过交费通知书检查: SMS ID={sms.id}")
            return result

        if not document_paths:
            logger.info(f"无文书文件,跳过交费通知书检查: SMS ID={sms.id}")
            return result

        logger.info(f"开始检查交费通知书: SMS ID={sms.id}, 文件数={len(document_paths)}")

        # 获取案件比对信息
        case_info = self.comparison_service.get_case_info_for_comparison(cast(int, sms.case.id)) # type: ignore
        result.case_name = case_info.case_name
        result.case_number = case_info.case_number
        result.cause_of_action = case_info.cause_of_action_name
        result.target_amount = case_info.target_amount

        # 筛选可能是交费通知书的PDF文件
        fee_notice_files = self._filter_fee_notice_files(document_paths)

        if not fee_notice_files:
            logger.info(f"未发现交费通知书文件: SMS ID={sms.id}")
            return result

        logger.info(f"发现 {len(fee_notice_files)} 个可能的交费通知书文件: SMS ID={sms.id}")

        # 提取并比对每个文件
        for file_path in fee_notice_files:
            check_item = self._check_single_file(file_path, cast(int, sms.case.id), case_info) # type: ignore
            if check_item:
                result.items.append(check_item)
                result.has_fee_notice = True

        logger.info(f"交费通知书检查完成: SMS ID={sms.id}, 发现 {len(result.items)} 份交费通知书")

        return result

    def _filter_fee_notice_files(self, document_paths: list[str]) -> list[str]:
        """
        筛选可能是交费通知书的文件

        通过文件名关键词初步筛选

        Args:
            document_paths: 文书文件路径列表

        Returns:
            可能是交费通知书的文件路径列表
        """
        fee_notice_files: list[Any] = []

        for file_path in document_paths:
            # 只处理PDF文件
            if not file_path.lower().endswith(".pdf"):
                continue

            file_name = Path(file_path).name

            # 检查文件名是否包含关键词
            for keyword in self.FEE_NOTICE_KEYWORDS:
                if keyword in file_name:
                    fee_notice_files.append(file_path)
                    logger.debug(f"文件名匹配交费通知书关键词: {file_name}")
                    break

        return fee_notice_files

    def _check_single_file(
        self,
        file_path: str,
        case_id: int,
        case_info: CaseComparisonInfo,
    ) -> FeeCheckItem | None:
        """
        检查单个文件

        Args:
            file_path: 文件路径
            case_id: 案件ID
            case_info: 案件比对信息

        Returns:
            FeeCheckItem 或 None
        """
        file_name = Path(file_path).name

        try:
            # 提取费用
            extraction_result = self.extraction_service.extract_from_files(
                file_paths=[],
                debug=False,
            )

            if not extraction_result.notices:
                logger.debug(f"文件未识别到交费通知书: {file_name}")
                return None

            # 取第一个识别结果
            notice = extraction_result.notices[0]
            amounts = notice.amounts

            # 创建检查项
            check_item = FeeCheckItem(
                file_name=file_name,
                file_path=file_path,
                extracted_acceptance_fee=amounts.acceptance_fee,
                extracted_preservation_fee=amounts.preservation_fee,
            )

            # 如果案件信息不完整,无法比对
            if not case_info.is_complete:
                check_item.can_compare = False
                check_item.compare_message = case_info.incomplete_reason
                logger.info(f"案件信息不完整,无法比对: {file_name}, 原因: {case_info.incomplete_reason}")
                return check_item

            # 进行费用比对
            comparison_result = self.comparison_service.compare_fee(
                case_id=case_id,
                extracted_acceptance_fee=amounts.acceptance_fee,
                extracted_preservation_fee=amounts.preservation_fee,
            )

            # 填充比对结果
            check_item.calculated_acceptance_fee = comparison_result.calculated_acceptance_fee
            check_item.calculated_acceptance_fee_half = comparison_result.calculated_acceptance_fee_half
            check_item.calculated_preservation_fee = comparison_result.calculated_preservation_fee
            check_item.acceptance_fee_match = comparison_result.acceptance_fee_match
            check_item.acceptance_fee_close = comparison_result.acceptance_fee_close
            check_item.acceptance_fee_diff = comparison_result.acceptance_fee_diff
            check_item.preservation_fee_match = comparison_result.preservation_fee_match
            check_item.preservation_fee_close = comparison_result.preservation_fee_close
            check_item.preservation_fee_diff = comparison_result.preservation_fee_diff
            check_item.can_compare = comparison_result.can_compare
            check_item.compare_message = comparison_result.message

            logger.info(
                f"交费通知书比对完成: {file_name}, "
                f"受理费匹配={check_item.acceptance_fee_match}, "
                f"视为一致={check_item.acceptance_fee_close}"
            )

            return check_item

        except Exception as e:
            logger.warning(f"检查交费通知书失败: {file_name}, 错误: {e!s}")
            return None

    def format_feishu_message(self, result: FeeCheckResult) -> str | None | None:
        """格式化飞书通知消息"""
        if not result.has_fee_notice or not result.items:
            return None

        lines: list[Any] = []

        for item in result.items:
            file_name = item.file_name[:27] + "..." if len(item.file_name) > 30 else item.file_name
            lines.append(f"📄 {file_name}")

            if not item.can_compare:
                lines.append(f"⚠️ {item.compare_message or '案件信息不完整'}")
                lines.append("")
                continue

            self._format_acceptance_fee_line(item, lines)
            self._format_preservation_fee_line(item, lines) # type: ignore
            lines.append("")

        return "\n".join(lines).strip()

    def _format_acceptance_fee_line(self, item: FeeCheckItem, lines: list[str]) -> None:
        """格式化受理费比对行"""
        if item.extracted_acceptance_fee is None:
            return
            return
        extracted = f"{item.extracted_acceptance_fee:,.0f}"
        calculated = f"{item.calculated_acceptance_fee:,.0f}" if item.calculated_acceptance_fee else "-"

        if item.acceptance_fee_match:
            lines.append(f"✅ 受理费一致: {extracted}元")
        elif item.acceptance_fee_close:
            lines.append(f"🟡 受理费视为一致: 提取{extracted}元 / 计算{calculated}元")
        else:
            diff = f"{abs(item.acceptance_fee_diff):,.0f}" if item.acceptance_fee_diff else "?"
            lines.append(f"❌ 受理费不一致: 提取{extracted}元 / 计算{calculated}元 (差{diff}元)")

        def _format_preservation_fee_line(item: FeeCheckItem, lines: list[str]) -> None:
            """格式化保全费比对行"""

        if item.extracted_preservation_fee is not None and item.extracted_preservation_fee > 0:
            extracted = f"{item.extracted_preservation_fee:,.0f}"
            calculated = f"{item.calculated_preservation_fee:,.0f}" if item.calculated_preservation_fee else "-"

            if item.preservation_fee_match:
                lines.append(f"✅ 保全费一致: {extracted}元")
            elif item.preservation_fee_close:
                lines.append(f"🟡 保全费视为一致: 提取{extracted}元 / 计算{calculated}元")
            else:
                diff = f"{abs(item.preservation_fee_diff):,.0f}" if item.preservation_fee_diff else "?"
                lines.append(f"❌ 保全费不一致: 提取{extracted}元 / 计算{calculated}元 (差{diff}元)")
        elif item.calculated_preservation_fee and item.calculated_preservation_fee > 0:
            calculated = f"{item.calculated_preservation_fee:,.0f}"
            lines.append(f"⚠️ 通知书无保全费,系统计算{calculated}元")
