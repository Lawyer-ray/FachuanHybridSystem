"""
常用的 Factory 组合

提供预配置的工厂组合，用于快速创建测试数据
"""

from .case_factories import CaseFactory, CasePartyFactory
from .client_factories import ClientFactory, NaturalPersonFactory
from .contract_factories import ContractFactory, ContractPaymentFactory
from .organization_factories import LawFirmFactory, LawyerFactory


def create_complete_case():
    """
    创建完整的案件（包含合同、律师、当事人）

    Returns:
        Case: 创建的案件对象
    """
    # 创建律所和律师
    law_firm = LawFirmFactory()
    lawyer = LawyerFactory(law_firm=law_firm)

    # 创建合同
    contract = ContractFactory(assigned_lawyer=lawyer)

    # 创建案件
    case = CaseFactory(contract=contract)

    # 创建当事人
    plaintiff = ClientFactory(is_our_client=True)
    defendant = ClientFactory(is_our_client=False)

    CasePartyFactory(case=case, client=plaintiff, legal_status="plaintiff")
    CasePartyFactory(case=case, client=defendant, legal_status="defendant")

    return case


def create_contract_with_payments(payment_count=3):
    """
    创建带有多笔收款的合同

    Args:
        payment_count: 收款笔数

    Returns:
        Contract: 创建的合同对象
    """
    contract = ContractFactory()

    for _ in range(payment_count):
        ContractPaymentFactory(contract=contract)

    return contract


def create_lawyer_with_cases(case_count=5):
    """
    创建带有多个案件的律师

    Args:
        case_count: 案件数量

    Returns:
        Lawyer: 创建的律师对象
    """
    lawyer = LawyerFactory()

    for _ in range(case_count):
        contract = ContractFactory(assigned_lawyer=lawyer)
        CaseFactory(contract=contract)

    return lawyer
