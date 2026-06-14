"""Unit tests for contracts.services.contract.contract_service_adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError


class TestContractServiceAdapterInit:
    """Test constructor."""

    def test_init_with_contract_service(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        cs = MagicMock()
        adapter = ContractServiceAdapter(contract_service=cs)
        assert adapter.contract_service is cs

    def test_init_requires_case_service_without_contract_service(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        with pytest.raises(RuntimeError, match="需要显式注入"):
            ContractServiceAdapter(contract_service=None, case_service=None)

    def test_init_with_case_service_creates_contract_service(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        case_svc = MagicMock()
        with patch(
            "apps.contracts.services.contract.contract_service_adapter.ContractService"
        ) as mock_cs_cls:
            mock_cs_cls.return_value = MagicMock()
            adapter = ContractServiceAdapter(contract_service=None, case_service=case_svc)
            mock_cs_cls.assert_called_once_with(case_service=case_svc)

    def test_default_assemblers_created(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        # Default assemblers should be non-None
        assert adapter.dto_assembler is not None
        assert adapter.details_assembler is not None

    def test_custom_assemblers_injected(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        dto_asm = MagicMock()
        details_asm = MagicMock()
        adapter = ContractServiceAdapter(
            contract_service=MagicMock(),
            dto_assembler=dto_asm,
            details_assembler=details_asm,
        )
        assert adapter.dto_assembler is dto_asm
        assert adapter.details_assembler is details_asm


class TestContractServiceAdapterGetContract:
    """get_contract tests."""

    def test_not_found_returns_none(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("not found")
        result = adapter.get_contract(1)
        assert result is None

    def test_found_returns_dto(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        dto_asm = MagicMock()
        adapter = ContractServiceAdapter(contract_service=MagicMock(), dto_assembler=dto_asm)
        contract_model = MagicMock()
        adapter.contract_service.query_service.get_contract_internal.return_value = contract_model
        expected_dto = MagicMock()
        dto_asm.to_dto.return_value = expected_dto
        result = adapter.get_contract(1)
        assert result is expected_dto


class TestContractServiceAdapterListContracts:
    """list_contracts delegates."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.list_contracts(foo="bar")
        adapter.contract_service.list_contracts.assert_called_once_with(foo="bar")


class TestContractServiceAdapterGetContractStages:
    """get_contract_stages tests."""

    def test_not_found_returns_empty(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nope")
        assert adapter.get_contract_stages(1) == []

    def test_returns_stages(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.representation_stages = ["stage1", "stage2"]
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.get_contract_stages(1) == ["stage1", "stage2"]

    def test_returns_empty_when_none(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.representation_stages = None
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.get_contract_stages(1) == []


class TestContractServiceAdapterValidateContractActive:
    """validate_contract_active tests."""

    def test_not_found_returns_false(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nope")
        assert adapter.validate_contract_active(1) is False

    def test_active_returns_true(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.status = "active"
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.validate_contract_active(1) is True

    def test_unsigned_returns_true(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.status = "unsigned"
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.validate_contract_active(1) is True

    def test_closed_returns_false(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.status = "closed"
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.validate_contract_active(1) is False


class TestContractServiceAdapterGetContractAssignedLawyerId:
    """get_contract_assigned_lawyer_id tests."""

    def test_not_found_returns_none(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.contract_service.query_service.get_contract_internal.side_effect = NotFoundError("nope")
        assert adapter.get_contract_assigned_lawyer_id(1) is None

    def test_returns_primary_lawyer_from_property(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        lawyer = MagicMock()
        lawyer.id = 42
        contract = MagicMock()
        contract.primary_lawyer = lawyer
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.get_contract_assigned_lawyer_id(1) == 42

    def test_falls_back_to_assignments(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        lawyer = MagicMock()
        lawyer.id = 99
        assignment = MagicMock()
        assignment.lawyer = lawyer
        contract = MagicMock()
        contract.primary_lawyer = None
        contract.assignments.filter.return_value.select_related.return_value.first.return_value = assignment
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.get_contract_assigned_lawyer_id(1) == 99

    def test_no_assignments_returns_none(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        contract = MagicMock()
        contract.primary_lawyer = None
        contract.assignments.filter.return_value.select_related.return_value.first.return_value = None
        contract.assignments.select_related.return_value.order_by.return_value.first.return_value = None
        adapter.contract_service.query_service.get_contract_internal.return_value = contract
        assert adapter.get_contract_assigned_lawyer_id(1) is None


class TestContractServiceAdapterGetContractLawyers:
    """get_contract_lawyers tests."""

    def test_returns_lawyer_dtos(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        lawyer = MagicMock()
        lawyer.id = 1
        contract = MagicMock()
        contract.all_lawyers = None
        assignment = MagicMock()
        assignment.lawyer = lawyer
        contract.assignments.select_related.return_value.order_by.return_value = [assignment]
        adapter.contract_service.query_service.get_contract_internal.return_value = contract

        with patch(
            "apps.contracts.services.contract.contract_service_adapter.LawyerDTO.from_model"
        ) as mock_dto:
            mock_dto.return_value = MagicMock()
            result = adapter.get_contract_lawyers(1)
            assert len(result) == 1


class TestContractServiceAdapterGetAllParties:
    """get_all_parties delegates."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.get_all_parties(1)
        adapter.contract_service.get_all_parties.assert_called_once_with(1)


class TestContractServiceAdapterGetContractWithDetailsInternal:
    """get_contract_with_details_internal tests."""

    def test_not_found_returns_none(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.contract_service.query_service.get_contract_with_details_model_internal.return_value = None
        assert adapter.get_contract_with_details_internal(1) is None

    def test_returns_assembled_dict(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        details_asm = MagicMock()
        adapter = ContractServiceAdapter(contract_service=MagicMock(), details_assembler=details_asm)
        model = MagicMock()
        adapter.contract_service.query_service.get_contract_with_details_model_internal.return_value = model
        expected_dict = {"name": "test"}
        details_asm.to_dict.return_value = expected_dict
        result = adapter.get_contract_with_details_internal(1)
        assert result == expected_dict


class TestContractServiceAdapterFeeModeDisplay:
    """get_fee_mode_display_internal tests."""

    def test_returns_display_value(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        with patch(
            "apps.contracts.models.contract.FeeMode"
        ) as mock_fee:
            mock_fee.choices = [("fixed", "固定收费"), ("hourly", "计时收费")]
            result = adapter.get_fee_mode_display_internal("fixed")
            assert result == "固定收费"

    def test_unknown_mode_returns_original(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        with patch(
            "apps.contracts.models.contract.FeeMode"
        ) as mock_fee:
            mock_fee.choices = [("fixed", "固定收费")]
            result = adapter.get_fee_mode_display_internal("unknown")
            assert result == "unknown"


class TestContractServiceAdapterGetOpposingParties:
    """get_opposing_parties_internal tests."""

    def test_filters_opposing(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        p1 = MagicMock(role_type="PRINCIPAL")
        p2 = MagicMock(role_type="OPPOSING")
        with patch.object(adapter, "get_party_roles_by_contract_internal", return_value=[p1, p2]):
            result = adapter.get_opposing_parties_internal(1)
            assert len(result) == 1
            assert result[0].role_type == "OPPOSING"


class TestContractServiceAdapterGetPrincipals:
    """get_principals_internal tests."""

    def test_filters_principals(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        p1 = MagicMock(role_type="PRINCIPAL")
        p2 = MagicMock(role_type="OPPOSING")
        with patch.object(adapter, "get_party_roles_by_contract_internal", return_value=[p1, p2]):
            result = adapter.get_principals_internal(1)
            assert len(result) == 1
            assert result[0].role_type == "PRINCIPAL"


class TestContractServiceAdapterDeleteContract:
    """delete_contract delegates."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        adapter.delete_contract(1)
        adapter.contract_service.delete_contract.assert_called_once_with(1)


class TestContractServiceAdapterContractModelInternal:
    """get_contract_model_internal tests."""

    def test_deprecation_warning(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        with (
            pytest.warns(DeprecationWarning, match="已弃用"),
            patch("apps.contracts.services.contract.contract_service_adapter.Contract") as mock_contract,
        ):
            mock_contract.objects.prefetch_related.return_value.get.return_value = MagicMock()
            adapter.get_contract_model_internal(1)


class TestContractServiceAdapterEnsureContractAccessCtx:
    """ensure_contract_access_ctx tests."""

    def test_delegates_to_internal(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        adapter = ContractServiceAdapter(contract_service=MagicMock())
        ctx = MagicMock()
        adapter.ensure_contract_access_ctx(1, ctx)
        adapter.contract_service.access_policy.ensure_access_ctx.assert_called_once_with(
            contract_id=1, ctx=ctx
        )
