"""
Factory Boy 工厂类

提供测试数据生成工厂
"""
from .organization_factories import LawFirmFactory, LawyerFactory, TeamFactory
from .client_factories import ClientFactory, ClientIdentityDocFactory
from .contract_factories import ContractFactory, ContractPaymentFactory
from .case_factories import CaseFactory, CasePartyFactory, CaseLogFactory
from .document_factories import DocumentTemplateFactory

__all__ = [
    'LawFirmFactory',
    'LawyerFactory',
    'TeamFactory',
    'ClientFactory',
    'ClientIdentityDocFactory',
    'ContractFactory',
    'ContractPaymentFactory',
    'CaseFactory',
    'CasePartyFactory',
    'CaseLogFactory',
    'DocumentTemplateFactory',
]
