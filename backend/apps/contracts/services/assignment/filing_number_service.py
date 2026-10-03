"""建档编号生成服务。"""

from __future__ import annotations

import logging
from typing import Any

from django.db import connection, transaction

from apps.core.exceptions import ConflictError, ValidationException
from apps.core.exceptions.error_codes import FILING_NUMBER_GENERATION_FAILED
from apps.core.models.enums import CaseType

logger = logging.getLogger("apps.contracts")

# 合同建档序号专用的 PostgreSQL 事务级咨询锁 key（固定 bigint，勿复用到其他业务）
_CONTRACT_FILING_SEQUENCE_LOCK_KEY = 8_801_001


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
                    message="合同类型不能为空", code="INVALID_CASE_TYPE", errors={"case_type": "合同类型不能为空"}
                )

            if not (1900 <= created_year <= 2100):
                raise ValidationException(
                    message="年份格式无效",
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
            logger.error("生成合同建档编号失败: %s", e, extra={"contract_id": contract_id}, exc_info=True)
            raise ConflictError(
                message="建档编号生成失败", code=FILING_NUMBER_GENERATION_FAILED, errors={"detail": str(e)}
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

    def _get_next_contract_sequence(self, year: int) -> int:  # pragma: no cover
        """
        获取合同的下一个序号(并发安全)

        策略(PostgreSQL 事务级咨询锁 + 取最大序号, 无需迁移):
        1. 用 pg_advisory_xact_lock 串行化同年份的并发建档——Django 聚合查询
           (count/max)会静默丢弃 select_for_update, 行级锁在这里无效
        2. 取当年已用编号的最大后缀而非 count, 删除中间序号的合同后
           也不会与存量编号冲突(旧 count+1 方案会造成该年度建档永久卡死)

        Args:
            year: 年份

        Returns:
            int: 下一个可用序号

        Requirements: 2.6, 7.3
        """
        from apps.contracts.models import Contract

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    # 事务级咨询锁：并发建档串行化（Django 聚合查询会丢弃
                    # select_for_update，行级锁对聚合无效）
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_CONTRACT_FILING_SEQUENCE_LOCK_KEY])

            # 取当年已用最大序号而非 count：删除中间序号也不会与存量冲突
            max_seq = 0
            for filing_number in (
                Contract.objects.filter(filing_number__startswith=f"{year}_", filing_number__isnull=False)
                .exclude(filing_number="")
                .values_list("filing_number", flat=True)
            ):
                parts = str(filing_number).split("_")
                if not parts[-1].isdigit():
                    # 脏数据防御：后缀不是纯数字（如手工录入的编号）时跳过
                    continue
                value = int(parts[-1])
                if value > max_seq:
                    max_seq = value

            return max_seq + 1

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

        return case_type_map.get(case_type, case_type)  # type: ignore[call-overload]
