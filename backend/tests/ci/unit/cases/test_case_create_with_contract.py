"""建案时挂归属合同：REST 入参与 service 两层都要真的把案件挂到项目下。

为什么单独钉这一条：`Case.contract` 是 FK，但 `CaseIn`（ModelSchema 白名单）原本
没有 `contract_id`，而 `CaseCommandService.create_case` 恰恰读 `data["contract_id"]`
做两件事——校验合同、解析并校验代理阶段。字段漏声明时 REST 建出来的案件会
**挂空合同**：项目页看不见、阶段校验也形同虚设，且不会报错。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from apps.cases.schemas.case_schemas import CaseIn
from apps.cases.services.case.case_command_service import CaseCommandService
from apps.contracts.models import Contract
from apps.core.exceptions import ValidationException


def _contract_stub(contract: Contract) -> Any:
    """只暴露 create_case 用到的三个能力：取合同、判是否激活、读阶段集合。"""

    def get_contract(cid: int) -> Contract | None:
        return contract if cid == contract.id else None

    def validate_contract_active(cid: int) -> bool:
        # 案件只能挂到 active 合同上（后端另有 CONTRACT_INACTIVE 分支，这里给 True）
        return cid == contract.id

    return SimpleNamespace(get_contract=get_contract, validate_contract_active=validate_contract_active)


@pytest.mark.django_db()
def test_case_in_keeps_contract_id() -> None:
    data = CaseIn(name="一审案件", contract_id=7).model_dump()
    assert data["contract_id"] == 7


@pytest.mark.django_db()
def test_create_case_links_contract(contract: Contract) -> None:
    contract.representation_stages = ["first_trial"]
    contract.save(update_fields=["representation_stages"])

    svc = CaseCommandService(contract_service=_contract_stub(contract))
    case = svc.create_case(
        {"name": "一审案件", "contract_id": contract.id, "current_stage": "first_trial"},
        perm_open_access=True,
    )

    assert case.contract_id == contract.id
    # 阶段走的是「按合同解析」那条路（合同勾了哪些代理阶段就只许建哪些）
    assert case.current_stage == "first_trial"


@pytest.mark.django_db()
def test_create_case_honours_start_date(contract: Contract) -> None:
    """收案日期可回填（二审/执行常要填真实收案日）；不填则走模型默认（今天）。"""
    svc = CaseCommandService(contract_service=_contract_stub(contract))

    dated = svc.create_case(
        {"name": "回填案件", "contract_id": contract.id, "start_date": date(2026, 7, 7)},
        perm_open_access=True,
    )
    assert dated.start_date == date(2026, 7, 7)

    today = svc.create_case({"name": "默认案件", "contract_id": contract.id}, perm_open_access=True)
    assert today.start_date == date.today()


@pytest.mark.django_db()
def test_create_case_rejects_stage_outside_contract(contract: Contract) -> None:
    contract.representation_stages = ["first_trial"]
    contract.save(update_fields=["representation_stages"])

    svc = CaseCommandService(contract_service=_contract_stub(contract))
    with pytest.raises(ValidationException, match="代理阶段"):
        svc.create_case(
            {"name": "二审案件", "contract_id": contract.id, "current_stage": "second_trial"},
            perm_open_access=True,
        )


@pytest.mark.django_db()
def test_create_case_rejects_unknown_contract() -> None:
    svc = CaseCommandService(contract_service=SimpleNamespace(get_contract=lambda _cid: None))
    with pytest.raises(ValidationException, match="合同不存在"):
        svc.create_case({"name": "孤儿案件", "contract_id": 999999}, perm_open_access=True)
