"""Tests for contracts/services/contract/contract_service.py — uncovered branches.

Covers: lazy property loading for all sub-services, delegated method calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestContractServiceInit:
    def test_default_init(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        assert svc.config is not None
        assert svc._case_service is None
        assert svc._mutation_service is None

    def test_custom_init(self):
        from apps.contracts.services.contract.contract_service import ContractService
        mock_config = MagicMock()
        svc = ContractService(config=mock_config)
        assert svc.config is mock_config


class TestContractServiceCaseServiceProperty:
    def test_raises_when_none(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_returns_injected(self):
        from apps.contracts.services.contract.contract_service import ContractService
        mock_cs = MagicMock()
        svc = ContractService(case_service=mock_cs)
        assert svc.case_service is mock_cs


class TestContractServiceLawyerAssignmentServiceProperty:
    def test_raises_when_none(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.lawyer_assignment_service

    def test_returns_injected(self):
        from apps.contracts.services.contract.contract_service import ContractService
        mock_las = MagicMock()
        svc = ContractService(lawyer_assignment_service=mock_las)
        assert svc.lawyer_assignment_service is mock_las


class TestContractServicePaymentServiceProperty:
    def test_lazy_load(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with patch("apps.contracts.services.payment.contract_payment_service.ContractPaymentService") as MockPS:
            MockPS.return_value = MagicMock()
            ps = svc.payment_service
            assert ps is svc._payment_service


class TestContractServiceSupplementaryAgreementProperty:
    def test_lazy_load(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with patch("apps.contracts.services.supplementary.supplementary_agreement_service.SupplementaryAgreementService") as MockSAS:
            MockSAS.return_value = MagicMock()
            sas = svc.supplementary_agreement_service
            assert sas is svc._supplementary_agreement_service


class TestContractServiceQueryServiceProperty:
    def test_lazy_load(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with patch("apps.contracts.services.contract.query.ContractQueryService") as MockQS:
            MockQS.return_value = MagicMock()
            qs = svc.query_service
            assert qs is svc._query_service


class TestContractServiceAccessPolicyProperty:
    def test_lazy_load(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with patch("apps.contracts.services.contract.domain.ContractAccessPolicy") as MockAP:
            MockAP.return_value = MagicMock()
            ap = svc.access_policy
            assert ap is svc._access_policy


class TestContractServiceDelegatedCalls:
    def test_create_contract(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc._mutation_service.create_contract.return_value = MagicMock()
        result = svc.create_contract({"name": "test"})
        assert result is not None

    def test_update_contract(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc._mutation_service.update_contract.return_value = MagicMock()
        result = svc.update_contract(1, {"name": "updated"})
        assert result is not None

    def test_delete_contract(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        svc._mutation_service = MagicMock()
        svc.delete_contract(1)
        svc._mutation_service.delete_contract.assert_called_once_with(1)

    def test_add_party(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        svc._party_service = MagicMock()
        svc.add_party(1, 2)
        svc._party_service.add_party.assert_called_once_with(contract_id=1, client_id=2)

    def test_remove_party(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        svc._party_service = MagicMock()
        svc.remove_party(1, 2)
        svc._party_service.remove_party.assert_called_once_with(contract_id=1, client_id=2)

    def test_get_all_parties(self):
        from apps.contracts.services.contract.contract_service import ContractService
        svc = ContractService()
        with patch("apps.contracts.services.contract.usecases.get_contract_all_parties.GetContractAllPartiesUseCase") as MockUC:
            MockUC.return_value.execute.return_value = [{"id": 1}]
            result = svc.get_all_parties(1)
            assert len(result) == 1
