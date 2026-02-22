"""Business logic services."""

from __future__ import annotations

import logging

from apps.cases.models import Case, CaseNumber
from apps.cases.utils import normalize_case_number as normalize_case_number_util

logger = logging.getLogger("apps.cases")


class CaseNumberInternalService:
    def add_case_number_internal(self, case_id: int, case_number: str, user_id: int | None = None) -> bool:
        if not case_number or not case_number.strip():
            return False

        normalized = normalize_case_number_util(case_number, ensure_hao=True)
        if not normalized:
            return False

        try:
            case = Case.objects.get(id=case_id)

            existing_numbers = CaseNumber.objects.filter(case_id=case_id)
            for existing in existing_numbers:
                if normalize_case_number_util(existing.number, ensure_hao=True) == normalized:
                    logger.info(
                        "案号已存在,跳过添加",
                        extra={
                            "action": "add_case_number_internal",
                            "case_id": case_id,
                            "case_number": case_number,
                            "normalized": normalized,
                        },
                    )
                    return True

            CaseNumber.objects.create(case=case, number=normalized)

            logger.info(
                "添加案号成功",
                extra={
                    "action": "add_case_number_internal",
                    "case_id": case_id,
                    "case_number": case_number,
                    "normalized": normalized,
                    "user_id": user_id,
                },
            )
            return True
        except Case.DoesNotExist:
            logger.error(
                "添加案号失败:案件不存在",
                extra={"action": "add_case_number_internal", "case_id": case_id, "case_number": case_number},
            )
            return False
        except Exception as e:
            logger.error(
                "添加案号失败: %s",
                e,
                extra={
                    "action": "add_case_number_internal",
                    "case_id": case_id,
                    "case_number": case_number,
                    "error": str(e),
                },
            )
            return False
