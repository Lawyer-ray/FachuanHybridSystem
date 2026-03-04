"""Module for error catalog."""

from __future__ import annotations

from .common import NotFoundError


def case_not_found(*, case_id: int) -> NotFoundError:
    return NotFoundError(message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": case_id})


def contract_not_found(*, contract_id: int) -> NotFoundError:
    return NotFoundError(message="合同不存在", code="CONTRACT_NOT_FOUND", errors={"contract_id": contract_id})


def evidence_list_not_found(*, list_id: int) -> NotFoundError:
    return NotFoundError(message="证据清单不存在", code="EVIDENCE_LIST_NOT_FOUND", errors={"list_id": list_id})


def evidence_item_not_found(*, item_id: int) -> NotFoundError:
    return NotFoundError(message="证据明细不存在", code="EVIDENCE_ITEM_NOT_FOUND", errors={"item_id": item_id})
