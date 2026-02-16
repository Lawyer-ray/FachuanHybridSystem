"""
Factory Boy 工厂类

提供测试数据生成工厂
"""

from .case_factories import CaseFactory, CaseLogFactory, CasePartyFactory
from .client_factories import ClientFactory, ClientIdentityDocFactory
from .contract_factories import ContractFactory, ContractPaymentFactory
from .document_factories import DocumentTemplateFactory
from .organization_factories import LawFirmFactory, LawyerFactory, TeamFactory

__all__ = [
    "LawFirmFactory",
    "LawyerFactory",
    "TeamFactory",
    "ClientFactory",
    "ClientIdentityDocFactory",
    "ContractFactory",
    "ContractPaymentFactory",
    "CaseFactory",
    "CasePartyFactory",
    "CaseLogFactory",
    "DocumentTemplateFactory",
]
