"""归档确认（contracts/services/archive/archive_query_service.confirm_archive）测试。

覆盖点：合同置 archived + 关联案件结案、已是 closed 的案件不重复写、
第二步写入失败时整体回滚（本次改造的核心价值）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.contracts.services.archive.archive_query_service import confirm_archive

_UPDATE_METHOD = "django.db.models.query.QuerySet.update"


def _make_contract(name: str = "归档确认合同") -> Contract:
    return Contract.objects.create(name=name, case_type="civil")


def _make_case(contract: Contract, name: str, status: str) -> Case:
    return Case.objects.create(name=name, contract=contract, status=status)


@pytest.mark.django_db
def test_confirm_archive_closes_contract_and_all_cases() -> None:
    contract = _make_contract()
    active_case = _make_case(contract, "在办案件", "active")

    assert confirm_archive(contract_id=contract.id) is True

    contract.refresh_from_db()
    active_case.refresh_from_db()
    assert contract.status == "archived"
    assert active_case.status == "closed"


@pytest.mark.django_db
def test_confirm_archive_skips_already_closed_cases() -> None:
    contract = _make_contract("已结案案件归档")
    already_closed = _make_case(contract, "早已结案", "closed")
    active_case = _make_case(contract, "在办案件", "active")

    assert confirm_archive(contract_id=contract.id) is True

    already_closed.refresh_from_db()
    active_case.refresh_from_db()
    assert already_closed.status == "closed"
    assert active_case.status == "closed"


@pytest.mark.django_db
def test_confirm_archive_rolls_back_contract_when_case_update_fails() -> None:
    """第二步（案件结案）抛异常时，第一步的合同 archived 必须一并回滚。"""
    contract = _make_contract("回滚合同")
    case = _make_case(contract, "在办案件", "active")

    # 允许合同 update 通过，随后案件 update 抛异常
    with patch(_UPDATE_METHOD, autospec=True, side_effect=[1, RuntimeError("案件结案写入失败")]):
        with pytest.raises(RuntimeError, match="案件结案写入失败"):
            confirm_archive(contract_id=contract.id)

    contract.refresh_from_db()
    case.refresh_from_db()
    assert contract.status == "active"
    assert case.status == "active"


@pytest.mark.django_db
def test_confirm_archive_returns_false_for_missing_contract() -> None:
    missing_id = 987654321

    assert not Contract.objects.filter(pk=missing_id).exists()
    assert confirm_archive(contract_id=missing_id) is False
