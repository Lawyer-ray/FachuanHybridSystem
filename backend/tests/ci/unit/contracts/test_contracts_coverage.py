"""contracts 模块 0% 覆盖率文件单元测试

覆盖文件:
- apps/contracts/domain/validators.py
- apps/contracts/schemas/base.py
- apps/contracts/services/admin_actions/contract_admin_action_service.py
- apps/contracts/services/admin_actions/wiring.py
- apps/contracts/services/archive/override_service.py
- apps/contracts/services/archive/wiring.py
- apps/contracts/services/assignment/wiring.py
- apps.contracts.services.contract.wiring.py
- apps/contracts/validators.py
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.exceptions import ValidationException

# ── domain/validators.py ────────────────────────────────────────


class TestNormalizeRepresentationStages:
    """normalize_representation_stages 函数测试"""

    def test_none_case_type_returns_empty(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages(None, ["一审", "二审"])
        assert result == []

    def test_invalid_case_type_returns_empty(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages("unknown_type", ["一审"])
        assert result == []

    def test_invalid_case_type_strict_with_stages_raises(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        with pytest.raises(ValidationException) as exc_info:
            normalize_representation_stages("unknown_type", ["一审"], strict=True)
        assert exc_info.value.code == "STAGES_NOT_APPLICABLE"

    def test_invalid_case_type_strict_empty_stages_no_raise(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages("unknown_type", [], strict=True)
        assert result == []

    def test_valid_case_type_with_valid_stages(self):
        from apps.contracts.domain.validators import normalize_representation_stages
        from apps.core.models.enums import CaseStage

        valid_stage = CaseStage.choices[0][0]
        result = normalize_representation_stages("civil", [valid_stage])
        assert result == [valid_stage]

    def test_valid_case_type_with_invalid_stages_raises(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        with pytest.raises(ValidationException) as exc_info:
            normalize_representation_stages("civil", ["不存在的阶段"])
        assert exc_info.value.code == "INVALID_STAGES"
        assert "不存在的阶段" in exc_info.value.errors["invalid_stages"]

    def test_none_stages_returns_empty(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages("civil", None)
        assert result == []

    def test_empty_string_case_type_returns_empty(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages("", ["一审"])
        assert result == []


# ── schemas/base.py ─────────────────────────────────────────────


class TestContractsSchemasBase:
    """contracts/schemas/base.py 模块导入测试"""

    def test_module_imports(self):
        import apps.contracts.schemas.base as mod

        assert hasattr(mod, "_logger")

    def test_logger_name(self):
        import apps.contracts.schemas.base as mod

        assert mod._logger.name == "apps.contracts"


# ── services/admin_actions/contract_admin_action_service.py ─────


class TestContractAdminActionService:
    """ContractAdminActionService 测试"""

    def _make_service(self):
        from apps.contracts.services.admin_actions.contract_admin_action_service import ContractAdminActionService

        case_service = MagicMock()
        case_assignment_service = MagicMock()
        svc = ContractAdminActionService(
            case_service=case_service,
            case_assignment_service=case_assignment_service,
        )
        return svc, case_service, case_assignment_service

    def test_unbind_cases_from_contract(self):
        svc, case_service, _ = self._make_service()
        case_service.unbind_cases_from_contract_internal.return_value = 5
        result = svc.unbind_cases_from_contract(1)
        assert result == 5
        case_service.unbind_cases_from_contract_internal.assert_called_once_with(1)

    def test_unbind_cases_from_contracts_multiple(self):
        svc, case_service, _ = self._make_service()
        case_service.unbind_cases_from_contract_internal.side_effect = [3, 2]
        result = svc.unbind_cases_from_contracts([10, 20])
        assert result == 5

    def test_unbind_cases_from_contracts_empty(self):
        svc, case_service, _ = self._make_service()
        result = svc.unbind_cases_from_contracts([])
        assert result == 0

    def test_sync_case_assignments_from_contract(self):
        svc, case_service, assignment_service = self._make_service()
        mock_case_1 = SimpleNamespace(id=101)
        mock_case_2 = SimpleNamespace(id=102)
        case_service.get_cases_by_contract.return_value = [mock_case_1, mock_case_2]

        svc.sync_case_assignments_from_contract(42, user="admin")

        case_service.get_cases_by_contract.assert_called_once_with(42)
        assert assignment_service.sync_assignments_from_contract.call_count == 2
        assignment_service.sync_assignments_from_contract.assert_any_call(
            case_id=101, user="admin", perm_open_access=True
        )

    def test_sync_case_assignments_no_user(self):
        svc, case_service, assignment_service = self._make_service()
        case_service.get_cases_by_contract.return_value = []
        svc.sync_case_assignments_from_contract(1)
        case_service.get_cases_by_contract.assert_called_once_with(1)


# ── services/admin_actions/wiring.py ────────────────────────────


class TestAdminActionsWiring:
    """admin_actions/wiring.py 工厂函数测试"""

    @patch("apps.contracts.services.admin_actions.wiring.ServiceLocator")
    def test_build_contract_admin_action_service(self, mock_locator):
        from apps.contracts.services.admin_actions.wiring import build_contract_admin_action_service

        mock_locator.get_case_service.return_value = MagicMock()
        mock_locator.get_case_assignment_service.return_value = MagicMock()

        svc = build_contract_admin_action_service()
        assert svc is not None
        assert hasattr(svc, "unbind_cases_from_contract")


# ── services/archive/override_service.py ────────────────────────


class TestArchiveOverrideService:
    """归档覆盖值 CRUD 服务测试"""

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_get_override_found(self, mock_model):
        from apps.contracts.services.archive.override_service import get_override

        mock_obj = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = mock_obj
        result = get_override(1, "subtype_a")
        assert result == mock_obj
        mock_model.objects.filter.assert_called_once_with(contract_id=1, template_subtype="subtype_a")

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_get_override_not_found(self, mock_model):
        from apps.contracts.services.archive.override_service import get_override

        mock_model.objects.filter.return_value.first.return_value = None
        result = get_override(999, "nonexistent")
        assert result is None

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_save_override(self, mock_model):
        from apps.contracts.services.archive.override_service import save_override

        mock_obj = MagicMock()
        mock_model.objects.update_or_create.return_value = (mock_obj, True)
        result, created = save_override(1, "subtype", {"key": "val"})
        assert result == mock_obj
        assert created is True
        mock_model.objects.update_or_create.assert_called_once_with(
            contract_id=1,
            template_subtype="subtype",
            defaults={"overrides": {"key": "val"}},
        )

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_delete_override(self, mock_model):
        from apps.contracts.services.archive.override_service import delete_override

        mock_model.objects.filter.return_value.delete.return_value = (2, {"some": 2})
        result = delete_override(1, "subtype")
        assert result == 2

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_delete_override_none_deleted(self, mock_model):
        from apps.contracts.services.archive.override_service import delete_override

        mock_model.objects.filter.return_value.delete.return_value = (0, {})
        result = delete_override(1, "subtype")
        assert result == 0


# ── services/archive/wiring.py ──────────────────────────────────


class TestArchiveWiring:
    """archive/wiring.py 工厂函数测试"""

    @patch("apps.contracts.services.archive.wiring.ArchiveChecklistService")
    def test_build_archive_checklist_service(self, MockSvc):
        from apps.contracts.services.archive.wiring import build_archive_checklist_service

        mock_instance = MagicMock()
        MockSvc.return_value = mock_instance
        result = build_archive_checklist_service()
        assert result == mock_instance


# ── services/assignment/wiring.py ───────────────────────────────


class TestAssignmentWiring:
    """assignment/wiring.py 工厂函数测试"""

    @patch("apps.contracts.services.assignment.wiring.ServiceLocator")
    def test_get_case_filing_number_service(self, mock_locator):
        from apps.contracts.services.assignment.wiring import get_case_filing_number_service

        mock_svc = MagicMock()
        mock_locator.get_case_filing_number_service.return_value = mock_svc
        result = get_case_filing_number_service()
        assert result == mock_svc


# ── services/contract/wiring.py ────────────────────────────


class TestCompositionUsecase:
    """wiring.py build_contract_service 测试"""

    @patch("apps.contracts.services.contract.query.ContractQueryFacade")
    @patch("apps.contracts.services.contract.domain.ContractAccessPolicy")
    @patch("apps.contracts.services.contract.query.ContractQueryService")
    def test_build_contract_service(self, MockQS, MockAP, MockQF):
        from apps.contracts.services.contract.wiring import build_contract_service

        case_svc = MagicMock()
        lawyer_svc = MagicMock()

        with patch("apps.contracts.services.assignment.lawyer_assignment_service.LawyerAssignmentService"):
            result = build_contract_service(case_service=case_svc, lawyer_service=lawyer_svc)
            assert result is not None


# ── validators.py (re-export) ───────────────────────────────────


class TestContractsValidatorsReExport:
    """contracts/validators.py 重导出测试"""

    def test_re_export(self):
        from apps.contracts.validators import normalize_representation_stages

        assert callable(normalize_representation_stages)
