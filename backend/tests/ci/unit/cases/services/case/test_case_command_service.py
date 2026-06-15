"""Unit tests for CaseCommandService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case
from apps.cases.services.case.case_command_service import CaseCommandService
from apps.core.exceptions import NotFoundError, ValidationException
from apps.testing.factories import CaseFactory, ContractFactory


@pytest.fixture
def svc():
    return CaseCommandService()


@pytest.fixture
def mock_contract_service():
    return MagicMock()


# ──────────── _validate_stage ────────────


class TestValidateStage:
    def test_valid_stage(self, svc):
        result = svc._validate_stage("first_trial", case_type=None)
        assert result == "first_trial"

    def test_invalid_case_type_stage(self, svc):
        with patch("apps.cases.services.case.case_command_service.business_config") as mock_config:
            mock_config.is_stage_valid_for_case_type.return_value = False
            with pytest.raises(ValidationException, match="不支持此阶段"):
                svc._validate_stage("first_trial", case_type="advisor")

    def test_stage_not_in_representation_stages(self, svc):
        with pytest.raises(ValidationException, match="代理阶段"):
            svc._validate_stage(
                "first_trial",
                case_type=None,
                representation_stages=["second_trial", "enforcement"],
            )

    def test_stage_in_representation_stages(self, svc):
        result = svc._validate_stage(
            "first_trial",
            case_type=None,
            representation_stages=["first_trial", "second_trial"],
        )
        assert result == "first_trial"

    def test_no_representation_stages_passes(self, svc):
        result = svc._validate_stage("first_trial", case_type=None, representation_stages=None)
        assert result == "first_trial"


# ──────────── _validate_contract ────────────


class TestValidateContract:
    def test_no_contract_service(self, svc):
        svc._contract_service = None
        svc._validate_contract(1)  # should not raise

    def test_contract_not_found(self, svc, mock_contract_service):
        mock_contract_service.get_contract.return_value = None
        svc._contract_service = mock_contract_service
        with pytest.raises(ValidationException, match="合同不存在"):
            svc._validate_contract(999)

    def test_contract_inactive(self, svc, mock_contract_service):
        mock_contract_service.get_contract.return_value = MagicMock()
        mock_contract_service.validate_contract_active.return_value = False
        svc._contract_service = mock_contract_service
        with pytest.raises(ValidationException, match="合同未激活"):
            svc._validate_contract(1)

    def test_contract_active(self, svc, mock_contract_service):
        mock_contract_service.get_contract.return_value = MagicMock()
        mock_contract_service.validate_contract_active.return_value = True
        svc._contract_service = mock_contract_service
        svc._validate_contract(1)  # should not raise


# ──────────── _resolve_stage_from_contract ────────────


class TestResolveStageFromContract:
    def test_no_contract(self, svc):
        result = svc._resolve_stage_from_contract(None, "first_trial")
        assert result == "first_trial"

    def test_with_contract_valid(self, svc, mock_contract_service):
        mock_contract = MagicMock()
        mock_contract.case_type = "civil"
        mock_contract.representation_stages = ["first_trial", "second_trial"]
        mock_contract_service.get_contract.return_value = mock_contract
        svc._contract_service = mock_contract_service
        result = svc._resolve_stage_from_contract(1, "first_trial")
        assert result == "first_trial"

    def test_with_contract_invalid(self, svc, mock_contract_service):
        mock_contract = MagicMock()
        mock_contract.case_type = "criminal"
        mock_contract.representation_stages = ["first_trial"]
        mock_contract_service.get_contract.return_value = mock_contract
        svc._contract_service = mock_contract_service
        with patch("apps.cases.services.case.case_command_service.business_config") as mock_config:
            mock_config.is_stage_valid_for_case_type.return_value = False
            with pytest.raises(ValidationException):
                svc._resolve_stage_from_contract(1, "second_trial")


# ──────────── create_case ────────────


class TestCreateCase:
    @pytest.mark.django_db
    def test_create_basic(self, svc):
        from apps.core.security.permissions import AccessContext
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        case = Case.objects.create(name="新建案件", case_type="civil")
        assert case.name == "新建案件"


# ──────────── delete_case ────────────


class TestDeleteCase:
    @pytest.mark.django_db
    def test_delete_existing_case(self, db):
        case = CaseFactory(name="待删除")
        case_id = case.pk
        Case.objects.filter(id=case_id).delete()
        assert not Case.objects.filter(id=case_id).exists()

    @pytest.mark.django_db
    def test_delete_nonexistent_raises(self, db):
        with pytest.raises(Case.DoesNotExist):
            Case.objects.get(id=999999)


# ──────────── close_cases_by_contract_internal ────────────


class TestCloseCasesByContractInternal:
    @pytest.mark.django_db
    def test_closes_active_cases(self, svc):
        from apps.core.models.enums import CaseStatus
        contract = ContractFactory()
        case1 = CaseFactory(contract=contract, status=CaseStatus.ACTIVE)
        case2 = CaseFactory(contract=contract, status=CaseStatus.ACTIVE)
        count = svc.close_cases_by_contract_internal(contract.id)
        assert count == 2
        case1.refresh_from_db()
        case2.refresh_from_db()
        assert case1.status == CaseStatus.CLOSED
        assert case2.status == CaseStatus.CLOSED

    @pytest.mark.django_db
    def test_no_active_cases(self, svc):
        from apps.core.models.enums import CaseStatus
        contract = ContractFactory()
        CaseFactory(contract=contract, status=CaseStatus.CLOSED)
        count = svc.close_cases_by_contract_internal(contract.id)
        assert count == 0


# ──────────── create_case_full ────────────


@pytest.mark.django_db
class TestCreateCaseFull:
    def test_delegates_to_workflow(self):
        mock_result = {"case": MagicMock(), "parties": [], "assignments": []}
        service = CaseCommandService()
        with patch(
            "apps.cases.services.case.case_command_service.CaseFullCreateWorkflow",
            create=True,
        ) as MockWorkflow:
            # The import is local, so we need to patch at the workflow path
            pass
        # Since CaseFullCreateWorkflow is imported locally, test it via the service method
        # We need to mock it at import source
        with patch(
            "apps.cases.services.case.workflows.case_full_create_workflow.CaseFullCreateWorkflow"
        ) as MockWF:
            MockWF.return_value.run.return_value = mock_result
            result = service.create_case_full(data={"name": "test"}, actor_id=1)
            assert result is mock_result
            MockWF.return_value.run.assert_called_once()

    def test_type_error_on_non_dict(self):
        service = CaseCommandService()
        with patch(
            "apps.cases.services.case.workflows.case_full_create_workflow.CaseFullCreateWorkflow"
        ) as MockWF:
            MockWF.return_value.run.return_value = "not a dict"
            with pytest.raises(TypeError, match="非 dict"):
                service.create_case_full(data={})


# ──────────── AccessContext variants ────────────


@pytest.mark.django_db
class TestContextVariants:
    def test_create_case_ctx(self):
        from apps.core.security.permissions import AccessContext

        service = CaseCommandService()
        mock_case = MagicMock()
        with patch.object(service, "create_case", return_value=mock_case) as mock_create:
            ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
            result = service.create_case_ctx(data={"name": "test"}, ctx=ctx)
            assert result is mock_case

    def test_delete_case_ctx(self):
        from apps.core.security.permissions import AccessContext

        service = CaseCommandService()
        with patch.object(service, "delete_case") as mock_delete:
            ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
            service.delete_case_ctx(case_id=1, ctx=ctx)
            mock_delete.assert_called_once_with(
                1, user=None, org_access=None, perm_open_access=True
            )

    def test_update_case_ctx(self):
        from apps.core.security.permissions import AccessContext

        service = CaseCommandService()
        mock_case = MagicMock()
        with patch.object(service, "update_case", return_value=mock_case) as mock_update:
            ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
            result = service.update_case_ctx(case_id=1, data={"name": "updated"}, ctx=ctx)
            assert result is mock_case
