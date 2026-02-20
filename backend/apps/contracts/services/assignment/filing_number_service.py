"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

import logging

"""
建档编号生成服务

职责:
- 生成合同建档编号
- 生成案件建档编号
- 管理序号分配
- 确保并发安全
"""

from typing import TYPE_CHECKING, Any

from django.db import connection, transaction

from apps.core.enums import CaseType
from apps.core.exceptions import ConflictError, ValidationException

if TYPE_CHECKING:
    pass

logger = logging.getLogger("apps.contracts")


class FilingNumberService:
    """
    建档编号生成服务

    职责:
    - 生成建档编号
    - 管理序号分配
    - 确保并发安全

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.3
    """

    def generate_contract_filing_number(self, contract_id: int, case_type: str, created_year: int) -> str:
        """
        生成合同建档编号

        格式: {年份}_{合同类型}_{HT}_{序号}
        示例: 2026_民商事_HT_1

        Args:
            contract_id: 合同ID
            case_type: 合同类型(从 CaseType 枚举获取)
            created_year: 合同创建年份

        Returns:
            str: 建档编号,格式: {年份}_{合同类型}_{HT}_{序号}

        Raises:
            ValidationException: 参数无效
            ConflictError: 编号生成冲突

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
        """
        try:
            # 参数验证
            if not case_type:
                raise ValidationException(
                    message=_("合同类型不能为空"), code="INVALID_CASE_TYPE", errors={"case_type": "合同类型不能为空"}
                )

            if not (1900 <= created_year <= 2100):
                raise ValidationException(
                    message=_("年份格式无效"),
                    code="INVALID_YEAR",
                    errors={"created_year": f"年份 {created_year} 超出有效范围"},
                )

            # 生成编号
            sequence = self._get_next_contract_sequence(created_year)
            case_type_label = self._format_case_type_label(case_type)
            filing_number = f"{created_year}_{case_type_label}_HT_{sequence}"

            logger.info(
                "生成合同建档编号成功",
                extra={
                    "contract_id": contract_id,
                    "filing_number": filing_number,
                    "action": "generate_contract_filing_number",
                },
            )

            return filing_number

        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"生成合同建档编号失败: {e!s}", extra={"contract_id": contract_id}, exc_info=True)
            raise ConflictError(
                message=_("建档编号生成失败"), code="FILING_NUMBER_GENERATION_FAILED", errors={"detail": str(e)}
            ) from e

    def generate_case_filing_number(self, case_id: int, case_type: str, created_year: int) -> Any:
        """
        生成案件建档编号

        格式: {年份}_{案件类型}_{AJ}_{序号}
        示例: 2026_民事_AJ_1

        Args:
            case_id: 案件ID
            case_type: 案件类型(从 SimpleCaseType 枚举获取)
            created_year: 案件创建年份

        Returns:
            str: 建档编号,格式: {年份}_{案件类型}_{AJ}_{序号}

        Raises:
            ValidationException: 参数无效
            ConflictError: 编号生成冲突

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
        """
        from .wiring import get_case_filing_number_service

        return get_case_filing_number_service().generate_case_filing_number_internal(
            case_id=case_id,
            case_type=case_type,
            created_year=created_year,
        )

    def _get_next_contract_sequence(self, year: int) -> int:
        """
        获取合同的下一个序号(并发安全)

        使用数据库行级锁确保序号唯一性

        策略:
        1. 使用 select_for_update() 锁定查询
        2. 统计当年已有建档编号的合同数量
        3. 返回 count + 1 作为新序号

        Args:
            year: 年份

        Returns:
            int: 下一个可用序号

        Requirements: 2.6, 7.3
        """
        from apps.contracts.models import Contract

        with transaction.atomic():
            qs = Contract.objects.filter(filing_number__startswith=f"{year}_", filing_number__isnull=False).exclude(
                filing_number=""
            )
            if connection.features.has_select_for_update:
                qs = qs.select_for_update()
            count = qs.count()

            return count + 1

    def _format_case_type_label(self, case_type: str) -> Any:
        """
        格式化合同类型标签(CaseType 枚举)

        将枚举值转换为中文标签

        Args:
            case_type: 案件类型枚举值

        Returns:
            str: 中文标签

        Requirements: 2.3, 2.4
        """
        # CaseType 枚举映射
        case_type_map = {
            CaseType.CIVIL: "民商事",
            CaseType.CRIMINAL: "刑事",
            CaseType.ADMINISTRATIVE: "行政",
            CaseType.LABOR: "劳动仲裁",
            CaseType.INTL: "商事仲裁",
            CaseType.SPECIAL: "专项服务",
            CaseType.ADVISOR: "常法顾问",
        }

        return case_type_map.get(case_type, case_type)
