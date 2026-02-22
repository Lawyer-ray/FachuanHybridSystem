import pytest
from django.utils import timezone

from apps.core.enums import CaseType
from apps.core.interfaces import ServiceLocator
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.django_db
class TestContractMutationFacadeAdminOps:
    def _build_contract_service(self):
        from apps.client.services import ClientServiceAdapter
        from apps.contracts.services import ContractPaymentService, ContractService, SupplementaryAgreementService  # type: ignore[attr-defined]
        from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService

        case_service = ServiceLocator.get_case_service()
        payment_service = ContractPaymentService()
        supplementary_agreement_service = SupplementaryAgreementService(client_service=ClientServiceAdapter())
        lawyer_assignment_service = LawyerAssignmentService(lawyer_service=ServiceLocator.get_lawyer_service())

        return ContractService(
            case_service=case_service,
            lawyer_assignment_service=lawyer_assignment_service,
            payment_service=payment_service,
            supplementary_agreement_service=supplementary_agreement_service,
        )

    def test_duplicate_contract_via_mutation_facade(self):
        admin_user = LawyerFactory(is_admin=True)
        contract = ContractFactory()

        service = self._build_contract_service()
        new_contract = service.mutation_facade.duplicate_contract(
            contract_id=contract.id,  # type: ignore[attr-defined]
            user=admin_user,
            org_access=None,
            perm_open_access=False,
        )

        assert new_contract.id != contract.id  # type: ignore[attr-defined]
        assert new_contract.name.endswith("(副本)")

    def test_renew_advisor_contract_via_mutation_facade(self):
        admin_user = LawyerFactory(is_admin=True)
        start = timezone.localdate()
        end = start.replace(year=start.year + 1)

        contract = ContractFactory(
            case_type=CaseType.ADVISOR,
            start_date=start,
            end_date=end,
        )

        service = self._build_contract_service()
        renewed = service.mutation_facade.renew_advisor_contract(
            contract_id=contract.id,  # type: ignore[attr-defined]
            user=admin_user,
            org_access=None,
            perm_open_access=False,
        )

        assert renewed.id != contract.id  # type: ignore[attr-defined]
        assert renewed.start_date == start.replace(year=start.year + 1)
        assert renewed.end_date == end.replace(year=end.year + 1)
