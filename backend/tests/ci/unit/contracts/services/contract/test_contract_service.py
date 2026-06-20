"""Unit tests for contracts.services.contract.contract_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestContractServiceInit:
    """Test constructor defaults."""

    def test_init_with_defaults(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc.config is not None
        assert svc._case_service is None
        assert svc._query_service is None
        assert svc._access_policy is None
        assert svc._mutation_facade is None

    def test_init_with_custom_config(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        config = MagicMock()
        svc = ContractService(config=config)
        assert svc.config is config

    def test_init_stores_case_service(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        cs = MagicMock()
        svc = ContractService(case_service=cs)
        assert svc._case_service is cs


class TestContractServiceCaseServiceProperty:
    """case_service property tests."""

    def test_raises_if_not_injected(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_returns_injected(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        cs = MagicMock()
        svc = ContractService(case_service=cs)
        assert svc.case_service is cs


class TestContractServiceLawyerAssignmentServiceProperty:
    """lawyer_assignment_service property tests."""

    def test_raises_if_not_injected(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.lawyer_assignment_service

    def test_returns_injected(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        las = MagicMock()
        svc = ContractService(lawyer_assignment_service=las)
        assert svc.lawyer_assignment_service is las


class TestContractServiceQueryServiceProperty:
    """query_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        # query_service is lazy-imported inside the method, so patch at the query module
        with patch("apps.contracts.services.contract.query.ContractQueryService") as mock_qs:
            mock_qs.return_value = MagicMock()
            result = svc.query_service
            mock_qs.assert_called_once()


class TestContractServiceAccessPolicyProperty:
    """access_policy lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        # access_policy is lazy-imported inside the method, so patch at the domain module
        with patch("apps.contracts.services.contract.domain.ContractAccessPolicy") as mock_ap:
            mock_ap.return_value = MagicMock()
            result = svc.access_policy
            mock_ap.assert_called_once()


class TestContractServiceAdminMutationServiceProperty:
    """admin_mutation_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        with patch(
            "apps.contracts.services.contract.contract_service.ContractAdminMutationService"
        ) as mock_ams:
            mock_ams.return_value = MagicMock()
            result = svc.admin_mutation_service
            mock_ams.assert_called_once()


class TestContractServiceValidatorProperty:
    """validator lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        with patch("apps.contracts.services.contract.contract_service.ContractValidator") as mock_v:
            mock_v.return_value = MagicMock()
            result = svc.validator
            mock_v.assert_called_once_with(svc.config)


class TestContractServiceDelegationMethods:
    """Test delegation methods."""

    def test_create_contract_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc.create_contract({"name": "test"})
        svc._mutation_service.create_contract.assert_called_once_with({"name": "test"})

    def test_update_contract_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc.update_contract(1, {"name": "test"})
        svc._mutation_service.update_contract.assert_called_once_with(1, {"name": "test"})

    def test_delete_contract_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc.delete_contract(1)
        svc._mutation_service.delete_contract.assert_called_once_with(1)

    def test_get_finance_summary_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._finance_mutation_service = MagicMock()
        svc.get_finance_summary(1)
        svc._finance_mutation_service.get_finance_summary.assert_called_once_with(1)

    def test_add_party_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._party_service = MagicMock()
        svc.add_party(1, 10)
        svc._party_service.add_party.assert_called_once_with(contract_id=1, client_id=10)

    def test_remove_party_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._party_service = MagicMock()
        svc.remove_party(1, 10)
        svc._party_service.remove_party.assert_called_once_with(contract_id=1, client_id=10)

    def test_update_contract_lawyers_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc.update_contract_lawyers(1, [10, 20])
        svc._mutation_service.update_contract_lawyers.assert_called_once_with(1, [10, 20])

    def test_create_contract_with_cases_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._workflow_service = MagicMock()
        svc.create_contract_with_cases(
            contract_data={"name": "c"},
            cases_data=[],
            assigned_lawyer_ids=[],
            payments_data=[],
            confirm_finance=False,
            user=None,
        )
        svc._workflow_service.create_contract_with_cases.assert_called_once()

    def test_update_contract_with_finance_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._finance_mutation_service = MagicMock()
        svc.update_contract_with_finance(
            contract_id=1,
            update_data={"name": "x"},
            user=None,
            confirm_finance=False,
            new_payments=[],
        )
        svc._finance_mutation_service.update_contract_with_finance.assert_called_once()

    def test_add_payments_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        svc._finance_mutation_service = MagicMock()
        svc.add_payments(contract_id=1, payments_data=[], user=None, confirm=True)
        svc._finance_mutation_service.add_payments.assert_called_once()

    def test_get_all_parties_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        mock_contract = MagicMock()
        mock_party = MagicMock()
        mock_party.client.id = 1
        mock_party.client.name = "客户A"
        mock_party.role = "client"
        mock_contract.contract_parties.select_related.return_value.all.return_value = [mock_party]
        mock_contract.supplementary_agreements.prefetch_related.return_value.all.return_value = []

        svc._query_service = MagicMock()
        svc._query_service.get_contract_internal.return_value = mock_contract

        result = svc.get_all_parties(1)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["source"] == "contract"


class TestContractServiceSupplementaryAgreementQueryServiceProperty:
    """supplementary_agreement_query_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        with patch(
            "apps.contracts.services.contract.query.SupplementaryAgreementQueryService"
        ) as mock_s:
            mock_s.return_value = MagicMock()
            result = svc.supplementary_agreement_query_service
            mock_s.assert_called_once()
