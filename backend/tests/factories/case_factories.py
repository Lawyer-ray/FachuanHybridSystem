"""
Case 模块的 Factory 类
"""
import factory
from factory.django import DjangoModelFactory
from decimal import Decimal
from django.utils import timezone
from apps.cases.models import (
    Case, CaseParty, CaseLog, CaseNumber,
    CaseStatus, CaseStage, LegalStatus, SimpleCaseType
)
from .contract_factories import ContractFactory
from .client_factories import ClientFactory
from .organization_factories import LawyerFactory


class CaseFactory(DjangoModelFactory):
    """案件工厂"""
    
    class Meta:
        model = Case
    
    contract = factory.SubFactory(ContractFactory)
    is_archived = False
    name = factory.Sequence(lambda n: f"测试案件{n}")
    status = CaseStatus.ACTIVE
    start_date = factory.LazyFunction(timezone.localdate)
    cause_of_action = "合同纠纷"
    target_amount = Decimal('100000.00')
    case_type = SimpleCaseType.CIVIL
    current_stage = CaseStage.FIRST_TRIAL


class CaseNumberFactory(DjangoModelFactory):
    """案号工厂"""
    
    class Meta:
        model = CaseNumber
    
    case = factory.SubFactory(CaseFactory)
    number = factory.Sequence(lambda n: f"（2024）粤01民初{n:05d}号")
    remarks = factory.Faker('sentence', locale='zh_CN')


class CasePartyFactory(DjangoModelFactory):
    """案件当事人工厂"""
    
    class Meta:
        model = CaseParty
    
    case = factory.SubFactory(CaseFactory)
    client = factory.SubFactory(ClientFactory)
    legal_status = LegalStatus.PLAINTIFF


class CaseLogFactory(DjangoModelFactory):
    """案件日志工厂"""
    
    class Meta:
        model = CaseLog
    
    case = factory.SubFactory(CaseFactory)
    content = factory.Faker('text', locale='zh_CN')
    actor = factory.SubFactory(LawyerFactory)
