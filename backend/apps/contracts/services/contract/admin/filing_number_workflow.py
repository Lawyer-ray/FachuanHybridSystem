"""Business workflow orchestration."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.contracts.models import Contract


class ContractFilingNumberWorkflow:
    def __init__(self, *, filing_number_service: Any) -> None:
        self.filing_number_service = filing_number_service

    def ensure_filing_number(self, *, contract: Contract) -> Any:
        if contract.filing_number:
            return contract.filing_number

        if contract.specified_date:
            created_year = contract.specified_date.year
        else:
            created_year = timezone.localdate().year

        # 必须走 assign_filing_number：它把「取号 + 写回」放进同一个事务，
        # pg_advisory_xact_lock 才真正覆盖到 UPDATE。原实现先调
        # generate_*(内部 atomic 已提交、锁已释放) 再在外部 save()，
        # 并发建档会拿到同一序号并撞 unique=True。
        return self.filing_number_service.assign_filing_number(contract, created_year=created_year)
