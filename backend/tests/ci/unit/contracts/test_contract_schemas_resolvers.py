"""Tests for contracts.schemas.contract_schemas and related resolvers."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from apps.contracts.schemas.contract_schemas import (
    ClientPaymentRecordOut,
    ContractAssignmentOut,
    ContractIn,
    FinalizedMaterialOut,
    UpdateLawyersIn,
)
from apps.contracts.models import FeeMode


class TestFinalizedMaterialOut:
    def test_resolve_category_label_with_display(self) -> None:
        obj = MagicMock()
        obj.get_category_display.return_value = "合同正本"
        assert FinalizedMaterialOut.resolve_category_label(obj) == "合同正本"

    def test_resolve_category_label_fallback(self) -> None:
        obj = MagicMock()
        obj.get_category_display.side_effect = AttributeError("no display")
        obj.category = "contract_original"
        assert FinalizedMaterialOut.resolve_category_label(obj) == "contract_original"

    def test_resolve_filename_with_path(self) -> None:
        obj = MagicMock()
        obj.file_path = "/media/docs/test.pdf"
        assert FinalizedMaterialOut.resolve_filename(obj) == "test.pdf"

    def test_resolve_filename_no_path(self) -> None:
        obj = MagicMock()
        obj.file_path = ""
        assert FinalizedMaterialOut.resolve_filename(obj) == ""

    def test_resolve_file_url_with_path(self) -> None:
        obj = MagicMock()
        obj.file_path = "docs/test.pdf"
        result = FinalizedMaterialOut.resolve_file_url(obj)
        assert "docs/test.pdf" in result

    def test_resolve_file_url_no_path(self) -> None:
        obj = MagicMock()
        obj.file_path = ""
        assert FinalizedMaterialOut.resolve_file_url(obj) == ""

    def test_resolve_uploaded_at_with_value(self) -> None:
        obj = MagicMock()
        obj.uploaded_at.isoformat.return_value = "2024-01-01T00:00:00"
        assert FinalizedMaterialOut.resolve_uploaded_at(obj) == "2024-01-01T00:00:00"

    def test_resolve_uploaded_at_none(self) -> None:
        obj = MagicMock()
        obj.uploaded_at = None
        assert FinalizedMaterialOut.resolve_uploaded_at(obj) is None

    def test_resolve_created_at_with_value(self) -> None:
        obj = MagicMock()
        obj.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        assert FinalizedMaterialOut.resolve_created_at(obj) == "2024-01-01T00:00:00"

    def test_resolve_created_at_no_attr(self) -> None:
        obj = SimpleNamespace(created_at=None)
        assert FinalizedMaterialOut.resolve_created_at(obj) is None


class TestClientPaymentRecordOut:
    def test_resolve_contract(self) -> None:
        obj = MagicMock()
        obj.contract_id = 42
        assert ClientPaymentRecordOut.resolve_contract(obj) == 42

    def test_resolve_amount(self) -> None:
        obj = MagicMock()
        obj.amount = 1234.56
        assert ClientPaymentRecordOut.resolve_amount(obj) == 1234.56

    def test_resolve_amount_none(self) -> None:
        obj = MagicMock()
        obj.amount = None
        assert ClientPaymentRecordOut.resolve_amount(obj) == 0.0

    def test_resolve_created_at(self) -> None:
        obj = MagicMock()
        obj.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        assert ClientPaymentRecordOut.resolve_created_at(obj) == "2024-01-01T00:00:00"

    def test_resolve_created_at_none(self) -> None:
        obj = MagicMock()
        obj.created_at = None
        assert ClientPaymentRecordOut.resolve_created_at(obj) is None


class TestUpdateLawyersIn:
    def test_valid_lawyer_ids(self) -> None:
        schema = UpdateLawyersIn(lawyer_ids=[1, 2, 3])
        assert schema.lawyer_ids == [1, 2, 3]

    def test_empty_lawyer_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="至少需要指派一个律师"):
            UpdateLawyersIn(lawyer_ids=[])


class TestContractAssignmentOut:
    def test_from_assignment(self) -> None:
        obj = MagicMock()
        obj.id = 1
        obj.lawyer_id = 10
        obj.lawyer.real_name = "张律师"
        obj.is_primary = True
        obj.order = 0
        result = ContractAssignmentOut.from_assignment(obj)
        assert result.lawyer_name == "张律师"
        assert result.is_primary is True

    def test_from_assignment_no_real_name(self) -> None:
        obj = MagicMock()
        obj.id = 1
        obj.lawyer_id = 10
        obj.lawyer.real_name = ""
        obj.lawyer.username = "zhang"
        obj.is_primary = False
        obj.order = 1
        result = ContractAssignmentOut.from_assignment(obj)
        assert result.lawyer_name == "zhang"

    def test_from_assignment_no_lawyer(self) -> None:
        obj = MagicMock()
        obj.id = 1
        obj.lawyer_id = 10
        obj.lawyer = None
        obj.is_primary = False
        obj.order = 1
        result = ContractAssignmentOut.from_assignment(obj)
        assert result.lawyer_name == ""


class TestContractInValidation:
    def test_fixed_fee_requires_amount(self) -> None:
        with pytest.raises(ValidationError, match="固定收费需填写金额"):
            ContractIn(
                name="Test",
                case_type="civil",
                lawyer_ids=[1],
                fee_mode=FeeMode.FIXED,
                fixed_amount=0,
            )

    def test_semi_risk_requires_both(self) -> None:
        with pytest.raises(ValidationError, match="半风险需填写前期金额"):
            ContractIn(
                name="Test",
                case_type="civil",
                lawyer_ids=[1],
                fee_mode=FeeMode.SEMI_RISK,
                fixed_amount=0,
                risk_rate=10,
            )

    def test_full_risk_requires_rate(self) -> None:
        with pytest.raises(ValidationError, match="全风险需填写风险比例"):
            ContractIn(
                name="Test",
                case_type="civil",
                lawyer_ids=[1],
                fee_mode=FeeMode.FULL_RISK,
                risk_rate=0,
            )

    def test_custom_requires_terms(self) -> None:
        with pytest.raises(ValidationError, match="自定义收费需填写条款文本"):
            ContractIn(
                name="Test",
                case_type="civil",
                lawyer_ids=[1],
                fee_mode=FeeMode.CUSTOM,
                custom_terms="",
            )


class TestContractOutResolvers:
    def test_resolve_case_type_label(self) -> None:
        obj = MagicMock()
        obj.get_case_type_display.return_value = "民事"
        from apps.contracts.schemas.contract_schemas import ContractOut
        assert ContractOut.resolve_case_type_label(obj) == "民事"

    def test_resolve_case_type_label_error(self) -> None:
        obj = MagicMock()
        obj.get_case_type_display.side_effect = AttributeError("err")
        from apps.contracts.schemas.contract_schemas import ContractOut
        assert ContractOut.resolve_case_type_label(obj) is None

    def test_resolve_status_label(self) -> None:
        obj = MagicMock()
        obj.get_status_display.return_value = "进行中"
        from apps.contracts.schemas.contract_schemas import ContractOut
        assert ContractOut.resolve_status_label(obj) == "进行中"

    def test_resolve_status_label_error(self) -> None:
        obj = MagicMock()
        obj.get_status_display.side_effect = ValueError("err")
        from apps.contracts.schemas.contract_schemas import ContractOut
        assert ContractOut.resolve_status_label(obj) is None

    def test_resolve_payments_success(self) -> None:
        obj = MagicMock()
        obj.payments.all.return_value = [MagicMock(), MagicMock()]
        from apps.contracts.schemas.contract_schemas import ContractOut
        result = ContractOut.resolve_payments(obj)
        assert len(result) == 2

    def test_resolve_payments_error(self) -> None:
        obj = MagicMock()
        obj.payments.all.side_effect = Exception("db error")
        from apps.contracts.schemas.contract_schemas import ContractOut
        result = ContractOut.resolve_payments(obj)
        assert result == []

    def test_resolve_representation_stages(self) -> None:
        obj = MagicMock()
        obj.representation_stages = ["first_instance", "second_instance"]
        from apps.contracts.schemas.contract_schemas import ContractOut
        result = ContractOut.resolve_representation_stages(obj)
        assert len(result) == 2
        assert all(isinstance(r, str) for r in result)

    def test_resolve_representation_stages_empty(self) -> None:
        obj = MagicMock()
        obj.representation_stages = None
        from apps.contracts.schemas.contract_schemas import ContractOut
        result = ContractOut.resolve_representation_stages(obj)
        assert result == []

    def test_resolve_contract_parties(self) -> None:
        obj = MagicMock()
        obj.contract_parties.all.return_value = [MagicMock()]
        from apps.contracts.schemas.contract_schemas import ContractOut
        result = ContractOut.resolve_contract_parties(obj)
        assert len(result) == 1
