"""Data repository layer."""

import logging
from typing import Any

logger = logging.getLogger("apps.automation")


class CaseLookupRepo:
    def __init__(self, case_service: Any) -> None:
        self.case_service = case_service

    def find_case_id_by_number(self, case_number: str) -> Any:
        if not case_number or not case_number.strip():
            logger.warning(
                "案号为空,无法查找案件", extra={"action": "find_case_id_by_number", "case_number": case_number}
            )
            return None

        try:
            cases = self.case_service.search_cases_by_case_number_internal(case_number)
            if not cases:
                logger.info("未找到案号匹配的案件", extra={})
                return None
            case_id = cases[0].id
            logger.info(
                "找到案号匹配的案件",
                extra={
                    "action": "find_case_id_by_number",
                    "case_number": case_number,
                    "case_id": case_id,
                    "match_count": len(cases),
                },
            )
            return case_id
        except Exception as e:
            logger.error(f"查找案件失败:{e}", extra={})
            return None
