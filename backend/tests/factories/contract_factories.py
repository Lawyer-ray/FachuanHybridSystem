"""
Contract 模块的 Factory 类
"""

from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractFinanceLog,
    ContractPayment,
    FeeMode,
    InvoiceStatus,
    LogLevel,
)
from apps.core.enums import CaseStatus, CaseType

from .organization_factories import LawyerFactory


class ContractFactory(DjangoModelFactory):
    """合同工厂"""

    class Meta:
        model = Contract

    name = factory.Sequence(lambda n: f"测试合同{n}")
    case_type = CaseType.CIVIL
    status = CaseStatus.ACTIVE
    specified_date = factory.LazyFunction(timezone.localdate)
    is_archived = False
    fee_mode = FeeMode.FIXED
    fixed_amount = Decimal("10000.00")
    representation_stages = factory.LazyFunction(lambda: ["first_trial"])


class ContractAssignmentFactory(DjangoModelFactory):
    """合同律师指派工厂"""

    class Meta:
        model = ContractAssignment

    contract = factory.SubFactory(ContractFactory)
    lawyer = factory.SubFactory(LawyerFactory)
    is_primary = True


class ContractPaymentFactory(DjangoModelFactory):
    """合同收款工厂"""

    class Meta:
        model = ContractPayment

    contract = factory.SubFactory(ContractFactory)
    amount = Decimal("5000.00")
    received_at = factory.LazyFunction(timezone.localdate)
    invoice_status = InvoiceStatus.UNINVOICED
    invoiced_amount = Decimal("0.00")
    note = factory.Faker("sentence", locale="zh_CN")


class ContractFinanceLogFactory(DjangoModelFactory):
    """财务日志工厂"""

    class Meta:
        model = ContractFinanceLog

    contract = factory.SubFactory(ContractFactory)
    action = factory.Sequence(lambda n: f"action_{n}")
    level = LogLevel.INFO
    actor = factory.SubFactory(LawyerFactory)
    payload = factory.LazyFunction(dict)
