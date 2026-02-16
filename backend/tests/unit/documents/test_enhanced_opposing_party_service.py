import pytest


@pytest.mark.django_db
def test_enhanced_opposing_party_uses_contract_opposing_party_ids():
    from apps.cases.models import Case, CaseParty
    from apps.client.models import Client
    from apps.contracts.models import Contract, ContractParty
    from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import EnhancedOpposingPartyService

    our_client = Client.objects.create(name="我方公司", legal_representative="张三", is_our_client=True)
    opposing_client = Client.objects.create(name="对方公司", legal_representative="李四", is_our_client=False)

    contract = Contract.objects.create(name="测试合同", case_type="civil")
    ContractParty.objects.create(contract=contract, client=our_client, role="PRINCIPAL")
    ContractParty.objects.create(contract=contract, client=opposing_client, role="OPPOSING")

    case = Case.objects.create(name="测试案件", contract=contract, cause_of_action="买卖合同纠纷-9132")
    CaseParty.objects.create(case=case, client=our_client, legal_status="defendant")
    CaseParty.objects.create(case=case, client=opposing_client, legal_status="plaintiff")

    service = EnhancedOpposingPartyService()
    result = service.generate({"contract": contract})["对方当事人名称案由与案件数量"]
    assert result == "对方公司买卖合同纠纷一案"


@pytest.mark.django_db
def test_enhanced_opposing_party_multiple_cases_formats_count():
    from apps.cases.models import Case, CaseParty
    from apps.client.models import Client
    from apps.contracts.models import Contract, ContractParty
    from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import EnhancedOpposingPartyService

    our_client = Client.objects.create(name="我方公司", legal_representative="张三", is_our_client=True)
    opposing_client = Client.objects.create(name="对方公司", legal_representative="李四", is_our_client=False)

    contract = Contract.objects.create(name="测试合同", case_type="civil")
    ContractParty.objects.create(contract=contract, client=our_client, role="PRINCIPAL")
    ContractParty.objects.create(contract=contract, client=opposing_client, role="OPPOSING")

    case1 = Case.objects.create(name="案1", contract=contract, cause_of_action="买卖合同纠纷-9132")
    case2 = Case.objects.create(name="案2", contract=contract, cause_of_action="租赁合同纠纷-9133")
    for c in (case1, case2):
        CaseParty.objects.create(case=c, client=our_client, legal_status="defendant")
        CaseParty.objects.create(case=c, client=opposing_client, legal_status="plaintiff")

    service = EnhancedOpposingPartyService()
    result = service.generate({"contract": contract})["对方当事人名称案由与案件数量"]
    assert "对方公司买卖合同纠纷" in result
    assert "对方公司租赁合同纠纷" in result
    assert result.endswith("两案")


@pytest.mark.django_db
def test_enhanced_opposing_party_falls_back_to_non_our_clients_when_contract_has_no_opposing():
    from apps.cases.models import Case, CaseParty
    from apps.client.models import Client
    from apps.contracts.models import Contract, ContractParty
    from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import EnhancedOpposingPartyService

    our_client = Client.objects.create(name="我方公司", legal_representative="张三", is_our_client=True)
    other_client = Client.objects.create(name="第三方", legal_representative="王五", is_our_client=False)

    contract = Contract.objects.create(name="测试合同", case_type="civil")
    ContractParty.objects.create(contract=contract, client=our_client, role="PRINCIPAL")

    case = Case.objects.create(name="测试案件", contract=contract, cause_of_action="合同纠纷-9131")
    CaseParty.objects.create(case=case, client=our_client, legal_status="plaintiff")
    CaseParty.objects.create(case=case, client=other_client, legal_status="defendant")

    service = EnhancedOpposingPartyService()
    result = service.generate({"contract": contract})["对方当事人名称案由与案件数量"]
    assert result == "第三方合同纠纷一案"

