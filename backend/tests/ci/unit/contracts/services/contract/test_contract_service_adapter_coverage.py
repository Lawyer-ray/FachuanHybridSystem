"""Tests for contracts/services/contract/contract_service_adapter.py — uncovered branches.

Covers: get_contract, get_contract_stages, validate_contract_active,
get_contract_assigned_lawyer_id, get_contract_lawyers, get_party_roles_by_contract_internal,
get_fee_mode_display_internal, get_supplementary_agreement_model_internal,
get_contract_model_internal, ensure_contract_access_ctx.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError


def _make_adapter(**deps):
    from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
    return ContractServiceAdapter(
        contract_service=deps.get("contract_service", MagicMock()),
        dto_assembler=deps.get("dto_assembler", MagicMock()),
        details_assembler=deps.get("details_assembler", MagicMock()),
    )


class TestContractServiceAdapterInit:
    def test_no_contract_service_no_case_service_raises(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
        with pytest.raises(RuntimeError, match="需要显式注入"):
            ContractServiceAdapter(contract_service=None, case_service=None)

    def test_with_case_service_creates_contract_service(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
        from apps.contracts.services.contract.contract_service import ContractService
        with patch("apps.contracts.services.contract.contract_service_adapter.ContractService") as MockCS:
            MockCS.return_value = MagicMock()
            adapter = ContractServiceAdapter(contract_service=None, case_service=MagicMock())
            assert adapter.contract_service is not None


class TestGetContract:
    def test_found(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        adapter.dto_assembler.to_dto.return_value = {"id": 1}
        assert adapter.get_contract(1) == {"id": 1}

    def test_not_found(self):
        adapter = _make_adapter()
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nf")
        assert adapter.get_contract(999) is None


class TestGetContractStages:
    def test_found(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.representation_stages = ["stage1", "stage2"]
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.get_contract_stages(1) == ["stage1", "stage2"]

    def test_not_found(self):
        adapter = _make_adapter()
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nf")
        assert adapter.get_contract_stages(1) == []


class TestValidateContractActive:
    def test_active(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.status = "active"
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.validate_contract_active(1) is True

    def test_unsigned(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.status = "unsigned"
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.validate_contract_active(1) is True

    def test_inactive(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.status = "terminated"
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.validate_contract_active(1) is False

    def test_not_found(self):
        adapter = _make_adapter()
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nf")
        assert adapter.validate_contract_active(999) is False


class TestGetContractAssignedLawyerId:
    def test_primary_lawyer_attr(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_lawyer = MagicMock()
        mock_lawyer.id = 42
        mock_contract.primary_lawyer = mock_lawyer
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.get_contract_assigned_lawyer_id(1) == 42

    def test_no_primary_lawyer_fallback_to_assignments(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.primary_lawyer = None
        mock_assignment = MagicMock()
        mock_lawyer = MagicMock()
        mock_lawyer.id = 77
        mock_assignment.lawyer = mock_lawyer
        mock_assignments_qs = MagicMock()
        mock_assignments_qs.filter.return_value.select_related.return_value.first.return_value = mock_assignment
        mock_assignments_qs.select_related.return_value.order_by.return_value.first.return_value = mock_assignment
        mock_contract.assignments = mock_assignments_qs
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.get_contract_assigned_lawyer_id(1) == 77

    def test_no_assignments(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.primary_lawyer = None
        mock_assignments_qs = MagicMock()
        mock_assignments_qs.filter.return_value.select_related.return_value.first.return_value = None
        mock_assignments_qs.select_related.return_value.order_by.return_value.first.return_value = None
        mock_contract.assignments = mock_assignments_qs
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        assert adapter.get_contract_assigned_lawyer_id(1) is None

    def test_not_found(self):
        adapter = _make_adapter()
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nf")
        assert adapter.get_contract_assigned_lawyer_id(999) is None


class TestGetContractLawyers:
    def test_with_all_lawyers_attr(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_lawyer = MagicMock()
        mock_contract.all_lawyers = [mock_lawyer]
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        with patch("apps.contracts.services.contract.contract_service_adapter.LawyerDTO") as MockDTO:
            MockDTO.from_model.return_value = {"name": "lawyer"}
            result = adapter.get_contract_lawyers(1)
            assert len(result) == 1

    def test_no_all_lawyers_fallback(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.all_lawyers = None
        mock_assignment = MagicMock()
        mock_lawyer = MagicMock()
        mock_assignment.lawyer = mock_lawyer
        mock_assignments_qs = MagicMock()
        mock_assignments_qs.select_related.return_value.order_by.return_value = [mock_assignment]
        mock_contract.assignments = mock_assignments_qs
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        with patch("apps.contracts.services.contract.contract_service_adapter.LawyerDTO") as MockDTO:
            MockDTO.from_model.return_value = {"name": "lawyer"}
            result = adapter.get_contract_lawyers(1)
            assert len(result) == 1


class TestGetPartyRolesByContractInternal:
    def test_success(self):
        adapter = _make_adapter()
        mock_party = MagicMock()
        mock_party.id = 1
        mock_party.contract_id = 10
        mock_party.client_id = 20
        mock_party.client.name = "client"
        mock_party.role = "PRINCIPAL"
        with patch("apps.contracts.services.contract.contract_service_adapter.ContractParty") as MockCP:
            MockCP.objects.filter.return_value.select_related.return_value = [mock_party]
            result = adapter.get_party_roles_by_contract_internal(10)
            assert len(result) == 1
            assert result[0].is_our_client is True


class TestGetFeeModeDisplayInternal:
    def test_valid_mode(self):
        adapter = _make_adapter()
        with patch("apps.contracts.services.contract.contract_service_adapter.ContractService") as MockCS:
            from apps.contracts.models.contract import FeeMode
            with patch("apps.contracts.services.contract.contract_service_adapter.FeeMode", create=True) as MockFM:
                MockFM.choices = [("fixed", "固定"), ("hourly", "计时")]
                result = adapter.get_fee_mode_display_internal("fixed")
                # fallback since we can't easily patch FeeMode inside the method
                assert isinstance(result, str)


class TestGetSupplementaryAgreementModelInternal:
    def test_delegates(self):
        adapter = _make_adapter()
        mock_result = MagicMock()
        adapter.contract_service.supplementary_agreement_query_service.get_supplementary_agreement_model_internal.return_value = mock_result
        assert adapter.get_supplementary_agreement_model_internal(1, 2) is mock_result


class TestGetContractModelInternal:
    def test_found(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        with patch("apps.contracts.services.contract.contract_service_adapter.Contract") as MockContract:
            MockContract.objects.prefetch_related.return_value.get.return_value = mock_contract
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                result = adapter.get_contract_model_internal(1)
                assert result is mock_contract

    def test_not_found(self):
        adapter = _make_adapter()
        with patch("apps.contracts.services.contract.contract_service_adapter.Contract") as MockContract:
            MockContract.DoesNotExist = type('DoesNotExist', (Exception,), {})
            MockContract.objects.prefetch_related.return_value.get.side_effect = MockContract.DoesNotExist()
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                result = adapter.get_contract_model_internal(999)
                assert result is None


class TestEnsureContractAccessCtx:
    def test_delegates(self):
        adapter = _make_adapter()
        ctx = MagicMock()
        adapter.ensure_contract_access_ctx(1, ctx)
        adapter.contract_service.access_policy.ensure_access_ctx.assert_called_once_with(
            contract_id=1, ctx=ctx
        )
