#!/usr/bin/env python
"""mock 一个非诉专项合同（阶段树 + 客户 + 主办律师），幂等。

对应原型 `frontend/prototype/2026.10.03-办案详情原型/54-办案详情-非诉专项.html`
的数据基准（开发库合同 393）：同名合同视为同一个 mock 对象，重复执行只刷新
阶段树与关键字段，不新建重复行。

    cd backend && .venv/bin/python devtools/mock_special_contract.py

为什么不是 management command：这不是业务命令，只是本地演示数据生成器，
不该出现在 `manage.py help` 的生产命令列表里。脚本自己完成 Django 引导。

阶段树按原型 `54-assets/data.js` 的 5 个阶段（尽职调查 / 方案设计 / 文件起草
[含 2 个子阶段] / 登记与注销 / 交割与移交），交付物带版本与落文件事实
（`planned` = 还没落文件），状态由 `derive_phase_states` 推出来，这里不手写。

隐私：客户与法定代表人姓名按仓库隐私规则改为「某」式虚构名，主办律师取库里
已有的真实账号（不新建律师，避免造出假账号）。
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "apiSystem"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()

from django.db import transaction

from apps.client.models import Client
from apps.contracts.models import Contract, ContractAssignment, ContractParty, FeeMode, PartyRole
from apps.core.models.enums import CaseType

CONTRACT_NAME = "佛山市禅城区环球不锈钢厂非诉专项（关厂、清盘）"
CLIENT_NAME = "佛山市禅城区某不锈钢厂"
LEGAL_REP = "张某"
START_DATE = date(2026, 10, 26)
END_DATE = date(2027, 4, 30)
FIXED_AMOUNT = Decimal("30000.00")
PRIMARY_LAWYER_USERNAME = "房长波"


def _deliverable(day: str, doc: str, ver: str, *, state: str, planned: bool) -> dict:
    return {"date": day, "doc": doc, "ver": ver, "state": state, "planned": planned}


STAGES: list[dict] = [
    {
        "key": "ph_dd",
        "name": "尽职调查",
        "acceptance": "《尽职调查报告》定稿（资产/债务/职工底数核清）",
        "templates": ["尽职调查清单模板", "尽调报告模板"],
        "date": "2026-10-26",
        "deliverables": [
            _deliverable("2026-10-27", "《关厂清盘尽职调查清单》", "v1", state="ok", planned=False),
            _deliverable("2026-10-29", "《尽职调查报告》", "v2", state="ok", planned=False),
        ],
        "children": [],
    },
    {
        "key": "ph_plan",
        "name": "方案设计",
        "acceptance": "关厂路径与顺序经客户书面确认",
        "templates": ["关厂方案模板"],
        "date": "2026-10-29",
        "deliverables": [
            _deliverable("2026-10-29", "《关厂与清盘方案》", "v1", state="ok", planned=False),
        ],
        "children": [],
    },
    {
        "key": "ph_draft",
        "name": "文件起草",
        "acceptance": "三件核心文书定稿",
        "templates": ["职工安置方案模板", "债权债务清理方案模板", "股东会决议模板"],
        "date": "2026-10-29",
        "deliverables": [],
        "children": [
            {
                "key": "ph_draft_staff",
                "name": "职工安置文书",
                "acceptance": "《职工安置方案》定稿",
                "templates": ["职工安置方案模板"],
                "date": "2026-10-29",
                "deliverables": [
                    _deliverable("2026-10-29", "《职工安置方案》", "v2", state="doing", planned=True),
                ],
                "children": [],
            },
            {
                "key": "ph_draft_debt",
                "name": "债权债务与决议",
                "acceptance": "《债权债务清理方案》与《股东会决议》定稿",
                "templates": ["债权债务清理方案模板", "股东会决议模板"],
                "date": "2026-10-28",
                "deliverables": [
                    _deliverable("2026-10-29", "《债权债务清理方案》", "v1", state="doing", planned=True),
                    _deliverable("2026-10-28", "《股东会决议（解散清算）》", "v1", state="ok", planned=False),
                ],
                "children": [],
            },
        ],
    },
    {
        "key": "ph_register",
        "name": "登记与注销",
        "acceptance": "市场监管注销登记完成",
        "templates": ["注销登记材料清单"],
        "date": "",
        "deliverables": [],
        "children": [],
    },
    {
        "key": "ph_close",
        "name": "交割与移交",
        "acceptance": "印章证照、档案与未了事务交接完毕",
        "templates": [],
        "date": "",
        "deliverables": [],
        "children": [],
    },
]


def _upsert_client() -> Client:
    client, _ = Client.objects.get_or_create(
        name=CLIENT_NAME,
        defaults={
            "client_type": Client.LEGAL,
            "legal_representative": LEGAL_REP,
            "address": "佛山市禅城区",
        },
    )
    return client


def _upsert_contract() -> tuple[Contract, bool]:
    contract, created = Contract.objects.get_or_create(
        name=CONTRACT_NAME,
        defaults={
            "case_type": CaseType.SPECIAL,
            "fee_mode": FeeMode.FIXED,
            "fixed_amount": FIXED_AMOUNT,
            "start_date": START_DATE,
            "end_date": END_DATE,
        },
    )
    # 幂等刷新：阶段树/金额/日期每次覆盖，避免旧版本 mock 留在库里
    contract.case_type = CaseType.SPECIAL
    contract.fee_mode = FeeMode.FIXED
    contract.fixed_amount = FIXED_AMOUNT
    contract.start_date = START_DATE
    contract.end_date = END_DATE
    contract.stages = STAGES
    contract.full_clean()
    contract.save()
    return contract, created


def _bind_party(contract: Contract, client: Client) -> None:
    ContractParty.objects.get_or_create(contract=contract, client=client, defaults={"role": PartyRole.PRINCIPAL})


def _bind_primary_lawyer(contract: Contract) -> str | None:
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.filter(username=PRIMARY_LAWYER_USERNAME).first()
    if lawyer is None:
        return None
    ContractAssignment.objects.update_or_create(
        contract=contract,
        lawyer=lawyer,
        defaults={"is_primary": True, "order": 0},
    )
    return str(lawyer.real_name or lawyer.username)


def mock() -> tuple[Contract, bool, str | None]:
    client = _upsert_client()
    with transaction.atomic():
        contract, created = _upsert_contract()
        _bind_party(contract, client)
        lawyer_name = _bind_primary_lawyer(contract)
    return contract, created, lawyer_name


def main() -> None:
    import logging

    contract, created, lawyer_name = mock()

    from apps.contracts.services.contract.stage_tree import derive_phase_states

    states = derive_phase_states(contract.stages)
    # 仓库 LOGGING 的 root 是 WARNING，`devtools` 这个 logger 会传播到 root 而被吞掉；
    # 本脚本的产出就是给开发者看的几行结果，直接挂 console handler 并关传播。
    log = logging.getLogger("devtools.mock_special_contract")
    log.handlers = [logging.StreamHandler(sys.stdout)]
    log.propagate = False
    log.setLevel(logging.INFO)

    log.info("%s非诉专项合同已就位", "新建：" if created else "已有（已刷新）：")
    log.info("  合同 id = %s", contract.id)
    log.info("  客户    = %s", CLIENT_NAME)
    log.info("  主办律师 = %s", lawyer_name or f"未找到（{PRIMARY_LAWYER_USERNAME}）")
    log.info("  阶段    = %s", " / ".join(f"{n['name']}={n['state']}" for n in states))
    log.info("  详情页  = http://localhost:5090/projects/%s", contract.id)


if __name__ == "__main__":
    main()
