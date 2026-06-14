"""contract_service_adapter.py — round3 tests for uncovered branches.

Covers:
- list_contracts, create_contract_with_cases, update_contract_with_finance,
  update_contract_lawyers, delete_contract
- get_contract_with_details_internal: found and not found
- get_opposing_parties_internal
- get_principals_internal
- get_supplementary_agreements_internal
- get_contract_lawyers: empty list
- get_fee_mode_display_internal: exception path
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError


def _make_adapter(**deps):
    from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
    return ContractServiceAdapter(
        contract_service=deps.get("contract_service", MagicMock()),
        dto_assembler=deps.get("dto_assembler", MagicMock()),
        details_assembler=deps.get("details_assembler", MagicMock()),
    )


# ── Delegation methods ────────────────────────────────────────────────────────


class TestDelegationMethods:
    def test_list_contracts(self):
        adapter = _make_adapter()
        adapter.contract_service.list_contracts.return_value = [{"id": 1}]
        assert adapter.list_contracts() == [{"id": 1}]

    def test_create_contract_with_cases(self):
        adapter = _make_adapter()
        adapter.contract_service.create_contract_with_cases.return_value = {"id": 2}
        result = adapter.create_contract_with_cases(name="test")
        assert result == {"id": 2}

    def test_update_contract_with_finance(self):
        adapter = _make_adapter()
        adapter.contract_service.update_contract_with_finance.return_value = True
        assert adapter.update_contract_with_finance(contract_id=1) is True

    def test_update_contract_lawyers(self):
        adapter = _make_adapter()
        adapter.contract_service.update_contract_lawyers.return_value = True
        assert adapter.update_contract_lawyers(contract_id=1, lawyers=[]) is True

    def test_delete_contract(self):
        adapter = _make_adapter()
        adapter.contract_service.delete_contract.return_value = None
        adapter.delete_contract(1)
        adapter.contract_service.delete_contract.assert_called_once_with(1)


# ── get_contract_with_details_internal ────────────────────────────────────────


class TestGetContractWithDetailsInternal:
    def test_found(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        adapter.contract_service.query_service.get_contract_with_details_model_internal.return_value = mock_contract
        adapter.details_assembler.to_dict.return_value = {"id": 1}
        result = adapter.get_contract_with_details_internal(1)
        assert result == {"id": 1}

    def test_not_found(self):
        adapter = _make_adapter()
        adapter.contract_service.query_service.get_contract_with_details_model_internal.return_value = None
        result = adapter.get_contract_with_details_internal(999)
        assert result is None


# ── get_opposing_parties_internal ─────────────────────────────────────────────


class TestGetOpposingPartiesInternal:
    def test_filters_opposing(self):
        adapter = _make_adapter()
        mock_party1 = MagicMock()
        mock_party1.role_type = "PRINCIPAL"
        mock_party2 = MagicMock()
        mock_party2.role_type = "OPPOSING"
        adapter.contract_service.get_all_parties = MagicMock(return_value=[])
        with patch.object(adapter, "get_party_roles_by_contract_internal", return_value=[mock_party1, mock_party2]):
            result = adapter.get_opposing_parties_internal(1)
            assert len(result) == 1
            assert result[0].role_type == "OPPOSING"


# ── get_principals_internal ──────────────────────────────────────────────────


class TestGetPrincipalsInternal:
    def test_filters_principals(self):
        adapter = _make_adapter()
        mock_party1 = MagicMock()
        mock_party1.role_type = "PRINCIPAL"
        mock_party2 = MagicMock()
        mock_party2.role_type = "OPPOSING"
        with patch.object(adapter, "get_party_roles_by_contract_internal", return_value=[mock_party1, mock_party2]):
            result = adapter.get_principals_internal(1)
            assert len(result) == 1
            assert result[0].role_type == "PRINCIPAL"


# ── get_supplementary_agreements_internal ─────────────────────────────────────


class TestGetSupplementaryAgreementsInternal:
    def test_delegates(self):
        adapter = _make_adapter()
        adapter.contract_service.supplementary_agreement_query_service.get_supplementary_agreements_internal.return_value = [
            {"id": 1}
        ]
        result = adapter.get_supplementary_agreements_internal(1)
        assert result == [{"id": 1}]


# ── get_contract_lawyers — empty list ────────────────────────────────────────


class TestGetContractLawyersEmpty:
    def test_empty_assignments(self):
        adapter = _make_adapter()
        mock_contract = MagicMock()
        mock_contract.all_lawyers = []
        adapter.contract_service.query_service.get_contract_internal.return_value = mock_contract
        with patch("apps.contracts.services.contract.contract_service_adapter.LawyerDTO") as MockDTO:
            result = adapter.get_contract_lawyers(1)
            assert result == []


# ── get_fee_mode_display_internal — exception path ───────────────────────────


class TestGetFeeModeDisplayInternalException:
    def test_exception_returns_raw_value(self):
        adapter = _make_adapter()
        # FeeMode is imported inside the method via from apps.contracts.models.contract import FeeMode
        # We need to patch it at the model import path
        with patch("apps.contracts.models.contract.FeeMode", side_effect=ImportError):
            result = adapter.get_fee_mode_display_internal("unknown_mode")
            assert result == "unknown_mode"


# ── get_party_roles_by_contract_internal — exception path ────────────────────


class TestGetPartyRolesException:
    def test_exception_propagates(self):
        adapter = _make_adapter()
        with patch("apps.contracts.services.contract.contract_service_adapter.ContractParty") as MockCP:
            MockCP.objects.filter.side_effect = Exception("db error")
            with pytest.raises(Exception, match="db error"):
                adapter.get_party_roles_by_contract_internal(1)
