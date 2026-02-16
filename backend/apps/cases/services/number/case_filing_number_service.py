"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.db import connection, transaction
from django.db.utils import OperationalError

from apps.cases.models import Case, CaseFilingNumberSequence  # type: ignore[attr-defined]
from apps.core.enums import SimpleCaseType
from apps.core.exceptions import ConflictError, ValidationException

logger = logging.getLogger("apps.cases")


class CaseFilingNumberService:
    def generate_case_filing_number_internal(self, case_id: int, case_type: str, created_year: int) -> str:
        try:
            if not case_type:
                raise ValidationException(
                    message="案件类型不能为空",
                    code="INVALID_CASE_TYPE",
                    errors={"case_type": "案件类型不能为空"},
                )

            if not (1900 <= created_year <= 2100):
                raise ValidationException(
                    message="年份格式无效",
                    code="INVALID_YEAR",
                    errors={"created_year": f"年份 {created_year} 超出有效范围"},
                )

            if not Case.objects.filter(id=case_id).exists():
                raise ValidationException(
                    message="案件不存在",
                    code="CASE_NOT_FOUND",
                    errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
                )

            try:
                sequence = self._get_next_case_sequence(created_year)
            except OperationalError as e:
                if "no such table: cases_casefilingnumbersequence" in str(e).lower():
                    logger.warning(
                        "建档编号序列表不存在,可能未执行数据库迁移",
                        extra={"case_id": case_id, "migration": "cases.0009_case_filing_number_sequence"},
                    )
                    raise ConflictError(
                        message="建档编号生成失败(数据库未迁移)",
                        code="FILING_NUMBER_MIGRATION_REQUIRED",
                        errors={
                            "detail": (
                                "缺少表 cases_casefilingnumbersequence,"
                                "请执行迁移 cases.0009_case_filing_number_sequence"
                            ),
                        },
                    ) from e
                raise
            case_type_label = self._format_simple_case_type_label(case_type)
            filing_number = f"{created_year}_{case_type_label}_AJ_{sequence}"

            logger.info(
                "生成案件建档编号成功",
                "生成案件建档编号成功",
                extra={
                    "case_id": case_id,
                    "filing_number": filing_number,
                    "action": "generate_case_filing_number_internal",
                },
            )

            return filing_number
        except ValidationException:
            raise
        except ConflictError:
            raise
        except Exception as e:
            logger.error(
                "生成案件建档编号失败",
                extra={"case_id": case_id, "error": str(e)},
                exc_info=True,
            )
            raise ConflictError(
                message="建档编号生成失败",
                code="FILING_NUMBER_GENERATION_FAILED",
                errors={"detail": str(e)},
            ) from e

    def _get_next_case_sequence(self, year: int) -> int:
        with transaction.atomic():
            qs = CaseFilingNumberSequence.objects
            if connection.features.has_select_for_update:
                qs = qs.select_for_update()
            seq, _created = qs.get_or_create(year=year, defaults={"next_value": 1})
            if _created:
                max_seq = 0
                for filing_number in (
                    Case.objects.filter(filing_number__startswith=f"{year}_", filing_number__isnull=False)
                    .exclude(filing_number="")
                    .values_list("filing_number", flat=True)
                ):
                    parts = str(filing_number).split("_")
                    if len(parts) < 4:
                        continue
                    try:
                        value = int(parts[-1])
                    except (TypeError, ValueError):
                        continue
                    if value > max_seq:
                        max_seq = value
                if max_seq >= int(seq.next_value or 1):
                    seq.next_value = max_seq + 1
                    seq.save(update_fields=["next_value", "updated_at"])
            value = int(seq.next_value or 1)
            seq.next_value = value + 1
            seq.save(update_fields=["next_value", "updated_at"])
            return value

    def _format_simple_case_type_label(self, case_type: str) -> Any:
        case_type_map = {
            SimpleCaseType.CIVIL: "民事",
            SimpleCaseType.ADMINISTRATIVE: "行政",
            SimpleCaseType.CRIMINAL: "刑事",
            SimpleCaseType.EXECUTION: "申请执行",
            SimpleCaseType.BANKRUPTCY: "破产",
        }
        return cast(Any, case_type_map.get(case_type, case_type))  # type: ignore
