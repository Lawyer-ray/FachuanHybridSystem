import pytest


@pytest.mark.django_db
def test_contract_access_policy_allows_assigned_lawyer():
    from apps.contracts.models import Contract, ContractAssignment
    from apps.contracts.services.contract.contract_access_policy import ContractAccessPolicy
    from apps.organization.models import LawFirm, Lawyer

    law_firm = LawFirm.objects.create(name="测试律所")
    lawyer = Lawyer.objects.create(username="u1", real_name="律师1", law_firm=law_firm)
    contract = Contract.objects.create(name="合同1", case_type="civil", status="active", representation_stages=["first_trial"])
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True)

    policy = ContractAccessPolicy()
    assert policy.has_access(contract_id=contract.id, user=lawyer, org_access=None, perm_open_access=False) is True


@pytest.mark.django_db
def test_contract_access_policy_denies_unassigned_lawyer():
    from apps.contracts.models import Contract
    from apps.contracts.services.contract.contract_access_policy import ContractAccessPolicy
    from apps.core.exceptions import PermissionDenied
    from apps.organization.models import LawFirm, Lawyer

    law_firm = LawFirm.objects.create(name="测试律所")
    lawyer = Lawyer.objects.create(username="u2", real_name="律师2", law_firm=law_firm)
    contract = Contract.objects.create(name="合同2", case_type="civil", status="active", representation_stages=["first_trial"])

    policy = ContractAccessPolicy()
    with pytest.raises(PermissionDenied):
        policy.ensure_access(contract_id=contract.id, user=lawyer, org_access=None, perm_open_access=False)
