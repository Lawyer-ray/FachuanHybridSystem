"""待认领发票的财务审计日志写入（``ContractFinanceLog``）。

裁定层（``invoice_intake_service``）与撤销时的清理子系统（``invoice_folder_cleanup``）
都要写这条日志，所以它单独落在**叶子模块**：两个上层模块都只往这里单向 import，
清理子系统不必反向依赖裁定层（依赖方向只能是「原模块 → 新模块」）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.contracts.models import InvoiceIntake

logger = logging.getLogger("apps.contracts")


def _log_finance(intake: InvoiceIntake, contract_id: int, action: str, user: Any, extra: dict[str, Any]) -> None:
    """写财务审计日志（失败不阻断主流程：日志记录本身不是业务成功条件）。

    S43-35（2026-11-23 二轮审计）：调用点都在 ``@transaction.atomic`` 内，且多见于
    ``return`` 前的最后几条语句（发票确认 :283、冲红重开）。原实现裸 try/except 吞掉
    日志 INSERT 的 DatabaseError——PG 上事务已 aborted，而 Django 6.1 不再置
    needs_rollback，外层 atomic 会去 commit()（PG 等价 ROLLBACK），于是整笔业务
    静默不落库、接口却报成功。现在把日志写入包进 savepoint，失败只回滚这一步。
    """
    try:
        from apps.contracts.models import ContractFinanceLog

        with transaction.atomic():
            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action=action,
                actor=user,
                payload={
                    "intake_id": intake.pk,
                    "invoice_number": intake.invoice_number,
                    "total_amount": str(intake.total_amount) if intake.total_amount is not None else "",
                    "operator_id": getattr(user, "pk", None),
                    **extra,
                },
            )
    except Exception:
        logger.warning("invoice_intake_finance_log_failed", extra={"intake_id": intake.pk}, exc_info=True)
