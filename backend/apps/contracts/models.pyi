"""
合同模块类型存根文件

为 Django ORM 动态属性提供类型定义，解决 mypy [attr-defined] 错误。
Requirements: 3.1, 3.2, 3.3
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models import Manager

from apps.client.models import Client
from apps.organization.models import Lawyer

class Contract(models.Model):
    # 主键
    id: int

    # 字段
    name: str
    case_type: str
    status: str
    specified_date: date
    start_date: date | None
    end_date: date | None
    is_archived: bool
    fee_mode: str
    fixed_amount: Decimal | None
    risk_rate: Decimal | None
    custom_terms: str | None
    representation_stages: list[str]

    # 反向关系
    contract_parties: Manager[ContractParty]
    assignments: Manager[ContractAssignment]
    payments: Manager[ContractPayment]
    finance_logs: Manager[ContractFinanceLog]
    reminders: Manager[ContractReminder]
    supplementary_agreements: Manager[SupplementaryAgreement]

    # Meta
    objects: Manager[Contract]

    def __str__(self) -> str: ...
    def clean(self) -> None: ...
    @property
    def primary_lawyer(self) -> Lawyer | None: ...
    @property
    def all_lawyers(self) -> list[Lawyer]: ...

class ContractParty(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    client_id: int
    client: Client
    role: str

    # Meta
    objects: Manager[ContractParty]

    def __str__(self) -> str: ...

class ContractAssignment(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    lawyer_id: int
    lawyer: Lawyer
    is_primary: bool
    order: int

    # Meta
    objects: Manager[ContractAssignment]

    def __str__(self) -> str: ...

class ContractPayment(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    amount: Decimal
    received_at: date
    invoice_status: str
    invoiced_amount: Decimal
    note: str | None
    created_at: datetime
    updated_at: datetime

    # Meta
    objects: Manager[ContractPayment]

    def __str__(self) -> str: ...

class ContractFinanceLog(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    action: str
    level: str
    actor_id: int
    actor: Lawyer
    payload: dict[str, Any]
    created_at: datetime

    # Meta
    objects: Manager[ContractFinanceLog]

    def __str__(self) -> str: ...

class ContractReminder(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    kind: str
    content: str
    due_date: date
    created_at: datetime

    # Meta
    objects: Manager[ContractReminder]

    def __str__(self) -> str: ...

class SupplementaryAgreement(models.Model):
    # 主键
    id: int

    # 字段
    contract_id: int
    contract: Contract
    name: str | None
    created_at: datetime
    updated_at: datetime

    # 反向关系
    parties: Manager[SupplementaryAgreementParty]

    # Meta
    objects: Manager[SupplementaryAgreement]

    def __str__(self) -> str: ...

class SupplementaryAgreementParty(models.Model):
    # 主键
    id: int

    # 字段
    supplementary_agreement_id: int
    supplementary_agreement: SupplementaryAgreement
    client_id: int
    client: Client
    role: str

    # Meta
    objects: Manager[SupplementaryAgreementParty]

    def __str__(self) -> str: ...
