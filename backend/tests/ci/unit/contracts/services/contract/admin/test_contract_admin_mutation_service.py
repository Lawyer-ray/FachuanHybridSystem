"""Unit tests for contracts.services.contract.admin.contract_admin_mutation_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.models.enums import CaseType




class TestContractAdminMutationServiceInit:
    """Test constructor and properties."""

    def test_init_with_defaults(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        assert svc._filing_number_service is None
        assert svc._case_service is None
        assert svc._reminder_service is None
        assert svc._clone_workflow is None
        assert svc._case_creation_workflow is None
        assert svc._filing_number_workflow is None

    def test_init_with_injected(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        fns = MagicMock()
        cs = MagicMock()
        rs = MagicMock()
        svc = ContractAdminMutationService(filing_number_service=fns, case_service=cs, reminder_service=rs)
        assert svc._filing_number_service is fns
        assert svc._case_service is cs
        assert svc._reminder_service is rs


class TestContractAdminMutationServiceCaseServiceProperty:
    """case_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.get_case_service"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            result = svc.case_service
            mock_get.assert_called_once()


class TestContractAdminMutationServiceReminderServiceProperty:
    """reminder_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.get_reminder_service"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            result = svc.reminder_service
            mock_get.assert_called_once()


class TestContractAdminMutationServiceCloneWorkflowProperty:
    """clone_workflow lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.ContractCloneWorkflow"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = svc.clone_workflow
            mock_cls.assert_called_once()


class TestContractAdminMutationServiceCaseCreationWorkflowProperty:
    """case_creation_workflow lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        svc._case_service = MagicMock()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.ContractCaseCreationWorkflow"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = svc.case_creation_workflow
            mock_cls.assert_called_once()


class TestContractAdminMutationServiceFilingNumberWorkflowProperty:
    """filing_number_workflow lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.ContractFilingNumberWorkflow"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = svc.filing_number_workflow
            mock_cls.assert_called_once()


class TestContractAdminMutationServiceCaseAllowedTypes:
    """CASE_ALLOWED_TYPES constant test."""

    def test_contains_expected_types(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        assert CaseType.CIVIL in ContractAdminMutationService.CASE_ALLOWED_TYPES
        assert CaseType.CRIMINAL in ContractAdminMutationService.CASE_ALLOWED_TYPES
        assert CaseType.ADMINISTRATIVE in ContractAdminMutationService.CASE_ALLOWED_TYPES
        assert CaseType.LABOR in ContractAdminMutationService.CASE_ALLOWED_TYPES
        assert CaseType.INTL in ContractAdminMutationService.CASE_ALLOWED_TYPES


@pytest.mark.django_db
class TestContractAdminMutationServiceDuplicateContract:
    """duplicate_contract tests."""

    def test_contract_not_found(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_cls.objects.get.side_effect = mock_cls.DoesNotExist()
            with pytest.raises(NotFoundError, match="合同不存在"):
                svc.duplicate_contract(1)

    def test_successful_duplicate(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        original = MagicMock()
        original.name = "原合同"
        original.case_type = CaseType.CIVIL
        original.status = "active"
        original.specified_date = None
        original.start_date = None
        original.end_date = None
        original.fee_mode = "fixed"
        original.fixed_amount = 1000
        original.risk_rate = 0
        original.custom_terms = ""
        original.representation_stages = []

        new_contract = MagicMock()
        mock_cw = MagicMock()
        svc._clone_workflow = mock_cw

        with (
            patch(
                "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
            ) as mock_cls,
        ):
            mock_cls.objects.get.return_value = original
            mock_cls.objects.create.return_value = new_contract
            result = svc.duplicate_contract(1)
            mock_cw.clone_related_data.assert_called_once_with(
                source_contract=original, target_contract=new_contract
            )


@pytest.mark.django_db
class TestContractAdminMutationServiceCreateCaseFromContract:
    """create_case_from_contract tests."""

    def test_contract_not_found(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_cls.objects.get.side_effect = mock_cls.DoesNotExist()
            with pytest.raises(NotFoundError, match="合同不存在"):
                svc.create_case_from_contract(contract_id=1)

    def test_invalid_case_type_raises(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        contract = MagicMock()
        contract.case_type = CaseType.ADVISOR  # not in CASE_ALLOWED_TYPES
        contract.get_case_type_display.return_value = "常法顾问"

        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.objects.get.return_value = contract
            with pytest.raises(ValidationException, match="不支持创建案件"):
                svc.create_case_from_contract(contract_id=1)

    def test_valid_civil_type(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        contract = MagicMock()
        contract.case_type = CaseType.CIVIL
        contract.pk = 1
        contract.name = "测试合同"
        contract.get_case_type_display.return_value = "民事"

        expected_dto = MagicMock()
        mock_cw = MagicMock()
        svc._case_creation_workflow = mock_cw
        mock_cw.create_case_from_contract.return_value = expected_dto

        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.objects.get.return_value = contract
            result = svc.create_case_from_contract(contract_id=1)
            assert result is expected_dto


class TestContractAdminMutationServiceGenerateAdvisorContractName:
    """generate_advisor_contract_name tests."""

    def test_correct_format(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService
        from datetime import date

        svc = ContractAdminMutationService()
        result = svc.generate_advisor_contract_name(
            principal_names=["甲公司", "乙公司"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assert "甲公司、乙公司" in result
        assert "2026年01月01日" in result
        assert "2026年12月31日" in result

    def test_single_principal(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService
        from datetime import date

        svc = ContractAdminMutationService()
        result = svc.generate_advisor_contract_name(
            principal_names=["甲公司"],
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
        )
        assert "甲公司" in result


@pytest.mark.django_db
class TestContractAdminMutationServiceHandleContractFilingChange:
    """handle_contract_filing_change tests."""

    def test_contract_not_found(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_cls.objects.get.side_effect = mock_cls.DoesNotExist()
            with pytest.raises(NotFoundError, match="合同不存在"):
                svc.handle_contract_filing_change(1, True)

    def test_unfile_returns_none(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        contract = MagicMock()
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.objects.get.return_value = contract
            result = svc.handle_contract_filing_change(1, False)
            assert result is None

    def test_already_has_filing_number(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        contract = MagicMock()
        contract.filing_number = "FN-001"
        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.objects.get.return_value = contract
            result = svc.handle_contract_filing_change(1, True)
            assert result == "FN-001"

    def test_generates_new_filing_number(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import ContractAdminMutationService

        svc = ContractAdminMutationService()
        contract = MagicMock()
        contract.filing_number = None
        mock_fnw = MagicMock()
        svc._filing_number_workflow = mock_fnw
        mock_fnw.ensure_filing_number.return_value = "FN-NEW"

        with patch(
            "apps.contracts.services.contract.admin.contract_admin_mutation_service.Contract"
        ) as mock_cls:
            mock_cls.objects.get.return_value = contract
            result = svc.handle_contract_filing_change(1, True)
            assert result == "FN-NEW"
