"""Comprehensive tests for cases services - command service, access policy, naming, etc."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.organization.models import Lawyer


# ── CaseAccessPolicy ────────────────────────────────────────────────────────


class TestCaseAccessPolicy:
    """cases/services/case/case_access_policy.py tests."""

    def _make_policy(self) -> Any:
        from apps.cases.services.case.case_access_policy import CaseAccessPolicy

        repo = MagicMock()
        return CaseAccessPolicy(case_assignment_repo=repo), repo

    def test_has_access_perm_open(self) -> None:
        policy, _ = self._make_policy()
        assert policy.has_access(1, None, None, perm_open_access=True) is True

    def test_has_access_no_user(self) -> None:
        policy, _ = self._make_policy()
        assert policy.has_access(1, None, None) is False

    def test_has_access_unauthenticated(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = False
        assert policy.has_access(1, user, None) is False

    def test_has_access_admin(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = True
        assert policy.has_access(1, user, None) is True

    def test_has_access_extra_cases(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = False
        policy.get_allowed_lawyer_ids = MagicMock(return_value=[])
        org_access = {"extra_cases": {42}}
        assert policy.has_access(42, user, org_access) is True

    def test_has_access_repo(self) -> None:
        policy, repo = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = 1
        policy.get_allowed_lawyer_ids = MagicMock(return_value=[1])
        repo.has_case_access.return_value = True
        assert policy.has_access(1, user, None) is True

    def test_has_access_no_allowed_lawyers(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = False
        policy.get_allowed_lawyer_ids = MagicMock(return_value=[])
        assert policy.has_access(1, user, None) is False

    def test_ensure_access_raises(self) -> None:
        from apps.core.exceptions import ForbiddenError

        policy, _ = self._make_policy()
        with pytest.raises(ForbiddenError):
            policy.ensure_access(case_id=1, user=None, org_access=None)

    def test_ensure_access_passes(self) -> None:
        policy, _ = self._make_policy()
        policy.ensure_access(
            case_id=1, user=None, org_access=None, perm_open_access=True
        )

    def test_can_access_authenticated(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        assert policy.can_access(user) is True

    def test_can_access_none(self) -> None:
        policy, _ = self._make_policy()
        assert policy.can_access(None) is False

    def test_filter_queryset_open_access(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        result = policy.filter_queryset(qs, None, None, perm_open_access=True)
        assert result == qs

    def test_filter_queryset_no_user(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        policy.filter_queryset(qs, None, None)
        qs.none.assert_called_once()

    def test_filter_queryset_admin(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = True
        result = policy.filter_queryset(qs, user, None)
        assert result == qs

    def test_get_extra_cases_empty(self) -> None:
        policy, _ = self._make_policy()
        assert policy._get_extra_cases(None) == set()

    def test_get_extra_cases_from_org_access(self) -> None:
        policy, _ = self._make_policy()
        assert policy._get_extra_cases({"extra_cases": {1, 2}}) == {1, 2}

    def test_get_extra_cases_list_convert(self) -> None:
        policy, _ = self._make_policy()
        result = policy._get_extra_cases({"extra_cases": [1, 2]})
        assert isinstance(result, set)

    def test_has_access_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        assert policy.has_access_ctx(case_id=1, ctx=ctx) is True

    def test_ensure_access_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        policy.ensure_access_ctx(case_id=1, ctx=ctx)

    def test_filter_queryset_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        qs = MagicMock()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        policy.filter_queryset_ctx(qs, ctx)


# ── ChatNameBuilder ─────────────────────────────────────────────────────────


class TestChatNameBuilder:
    """cases/services/chat/naming.py tests."""

    def test_build_basic(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder

        config_service = MagicMock()
        config_service.render_chat_name.return_value = "[一审] 测试案件"
        builder = ChatNameBuilder(config_service=config_service)

        case = MagicMock()
        case.name = "测试案件"
        case.current_stage = "first_trial"
        case.get_current_stage_display.return_value = "一审"
        case.case_type = "civil"
        case.get_case_type_display.return_value = "民事"
        case.id = 1

        result = builder.build(case=case)
        assert result == "[一审] 测试案件"
        config_service.render_chat_name.assert_called_once()

    def test_build_no_case_raises(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder
        from apps.core.exceptions import ValidationException

        builder = ChatNameBuilder(config_service=MagicMock())
        with pytest.raises(ValidationException):
            builder.build(case=None)

    def test_build_no_name_raises(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder
        from apps.core.exceptions import ValidationException

        builder = ChatNameBuilder(config_service=MagicMock())
        case = MagicMock()
        case.name = None
        with pytest.raises(ValidationException):
            builder.build(case=case)

    def test_build_with_stage_display_error(self) -> None:
        """When get_current_stage_display raises, falls back to raw value."""
        from apps.cases.services.chat.naming import ChatNameBuilder

        config_service = MagicMock()
        config_service.render_chat_name.return_value = "群聊名"
        builder = ChatNameBuilder(config_service=config_service)

        case = MagicMock()
        case.name = "案件名"
        case.current_stage = "first_trial"
        case.get_current_stage_display.side_effect = ValueError("bad")
        case.case_type = "civil"
        case.get_case_type_display.return_value = "民事"

        result = builder.build(case=case)
        assert result == "群聊名"

    def test_build_with_case_type_display_error(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder

        config_service = MagicMock()
        config_service.render_chat_name.return_value = "群聊名"
        builder = ChatNameBuilder(config_service=config_service)

        case = MagicMock()
        case.name = "案件名"
        case.current_stage = None
        case.case_type = "civil"
        case.get_case_type_display.side_effect = ValueError("bad")

        result = builder.build(case=case)
        assert result == "群聊名"

    def test_build_no_stage_no_type(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder

        config_service = MagicMock()
        config_service.render_chat_name.return_value = "群聊名"
        builder = ChatNameBuilder(config_service=config_service)

        case = MagicMock()
        case.name = "案件名"
        case.current_stage = None
        case.case_type = None

        result = builder.build(case=case)
        assert result == "群聊名"


# ── CaseCommandService ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseCommandService:
    """cases/services/case/case_command_service.py tests."""

    def _make_service(self) -> Any:
        from apps.cases.services.case.case_command_service import CaseCommandService

        contract_svc = MagicMock()
        access_policy = MagicMock()
        return CaseCommandService(
            contract_service=contract_svc, access_policy=access_policy
        ), contract_svc, access_policy

    def test_create_case_basic(self) -> None:
        from apps.core.security.access_context import AccessContext

        service, _, _ = self._make_service()
        contract = Contract.objects.create(name="cmd合同", case_type="civil")
        user = MagicMock()
        ctx = AccessContext(user=user, org_access=None, perm_open_access=True)
        case = service.create_case(
            {"name": "新案件", "contract": contract},
            user=user,
            perm_open_access=True,
        )
        assert case.name == "新案件"

    def test_create_case_with_contract_id(self) -> None:
        service, contract_svc, _ = self._make_service()
        contract = Contract.objects.create(name="cmd_contract合同", case_type="civil")
        mock_contract = MagicMock()
        mock_contract.case_type = "civil"
        mock_contract.representation_stages = []
        contract_svc.get_contract.return_value = mock_contract
        contract_svc.validate_contract_active.return_value = True

        user = MagicMock()
        case = service.create_case(
            {"name": "有合同案件", "contract": contract, "contract_id": contract.id},
            user=user,
            perm_open_access=True,
        )
        assert case.name == "有合同案件"

    def test_validate_contract_not_found(self) -> None:
        from apps.core.exceptions import ValidationException

        service, contract_svc, _ = self._make_service()
        contract_svc.get_contract.return_value = None
        with pytest.raises(ValidationException, match="合同不存在"):
            service._validate_contract(999)

    def test_validate_contract_inactive(self) -> None:
        from apps.core.exceptions import ValidationException

        service, contract_svc, _ = self._make_service()
        contract_svc.get_contract.return_value = MagicMock()
        contract_svc.validate_contract_active.return_value = False
        with pytest.raises(ValidationException, match="合同未激活"):
            service._validate_contract(1)

    def test_validate_contract_no_service(self) -> None:
        from apps.cases.services.case.case_command_service import CaseCommandService

        service = CaseCommandService(contract_service=None)
        service._validate_contract(1)  # Should not raise

    def test_validate_stage_valid(self) -> None:
        service, contract_svc, _ = self._make_service()
        from apps.core.config.business_config import business_config

        with patch.object(business_config, "is_stage_valid_for_case_type", return_value=True):
            result = service._validate_stage("first_trial", "civil")
            assert result == "first_trial"

    def test_validate_stage_invalid_case_type(self) -> None:
        from apps.core.exceptions import ValidationException

        service, _, _ = self._make_service()
        from apps.core.config.business_config import business_config

        with patch.object(business_config, "is_stage_valid_for_case_type", return_value=False):
            with pytest.raises(ValidationException):
                service._validate_stage("first_trial", "bankruptcy")

    def test_validate_stage_not_in_rep_stages(self) -> None:
        from apps.core.exceptions import ValidationException

        service, _, _ = self._make_service()
        from apps.core.config.business_config import business_config

        with patch.object(business_config, "is_stage_valid_for_case_type", return_value=True):
            with pytest.raises(ValidationException, match="代理阶段"):
                service._validate_stage("first_trial", "civil", ["second_trial"])

    def test_delete_case_not_found(self) -> None:
        from apps.core.exceptions import NotFoundError

        service, _, _ = self._make_service()
        with pytest.raises(NotFoundError):
            service.delete_case(999999, user=None, perm_open_access=True)

    def test_count_cases_by_contract(self) -> None:
        service, _, _ = self._make_service()
        contract = Contract.objects.create(name="count合同", case_type="civil")
        Case.objects.create(name="count1案件", contract=contract)
        Case.objects.create(name="count2案件", contract=contract)
        count = service.count_cases_by_contract(contract.id)
        assert count == 2

    def test_unbind_cases_from_contract(self) -> None:
        service, _, _ = self._make_service()
        contract = Contract.objects.create(name="unbind合同", case_type="civil")
        Case.objects.create(name="unbind1案件", contract=contract)
        Case.objects.create(name="unbind2案件", contract=contract)
        count = service.unbind_cases_from_contract_internal(contract.id)
        assert count == 2
        assert Case.objects.filter(contract=contract).count() == 0

    def test_close_cases_by_contract(self) -> None:
        service, _, _ = self._make_service()
        from apps.core.models.enums import CaseStatus

        contract = Contract.objects.create(name="close合同", case_type="civil")
        Case.objects.create(name="close1案件", contract=contract, status=CaseStatus.ACTIVE)
        Case.objects.create(name="close2案件", contract=contract, status=CaseStatus.CLOSED)
        count = service.close_cases_by_contract_internal(contract.id)
        assert count == 1

    def test_close_cases_by_contract_no_active(self) -> None:
        service, _, _ = self._make_service()
        from apps.core.models.enums import CaseStatus

        contract = Contract.objects.create(name="no_close合同", case_type="civil")
        Case.objects.create(name="no_close1案件", contract=contract, status=CaseStatus.CLOSED)
        count = service.close_cases_by_contract_internal(contract.id)
        assert count == 0


# ── CaseQueryOrchestrator ───────────────────────────────────────────────────


class TestCaseQueryOrchestrator:
    """cases/services/case/case_query_orchestrator.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_query_orchestrator import CaseQueryOrchestrator

        assert CaseQueryOrchestrator is not None


# ── Chat Provider Facade ────────────────────────────────────────────────────


class TestChatProviderFacade:
    """cases/services/chat/provider_facade.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.chat.provider_facade import ChatProviderFacade

        assert ChatProviderFacade is not None


# ── Case Service Adapter ────────────────────────────────────────────────────


class TestCaseServiceAdapter:
    """cases/services/case/case_service_adapter.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_service_adapter import CaseServiceAdapter

        assert CaseServiceAdapter is not None


# ── Template Match Policy ───────────────────────────────────────────────────


class TestTemplateMatchPolicyExtended:
    """More tests for template_match_policy."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.template_match_policy import CaseTemplateMatchPolicy

        assert CaseTemplateMatchPolicy is not None


# ── Case Search Service ─────────────────────────────────────────────────────


class TestCaseSearchService:
    """cases/services/case/case_search_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_search_service import CaseSearchService

        assert CaseSearchService is not None


# ── Case Import Service ─────────────────────────────────────────────────────


class TestCaseImportService:
    """cases/services/case_import_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case_import_service import CaseImportService

        assert CaseImportService is not None


# ── Cause Rule Service ──────────────────────────────────────────────────────


class TestCauseRuleService:
    """cases/services/data/cause_rule_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.data.cause_rule_service import CauseRuleService

        assert CauseRuleService is not None


# ── Case Log Services ───────────────────────────────────────────────────────


class TestCaseLogServices:
    """cases/services/log/ tests."""

    def test_caselog_service_importable(self) -> None:
        from apps.cases.services.log.caselog_service import CaseLogService

        assert CaseLogService is not None

    def test_case_log_mutation_service_importable(self) -> None:
        from apps.cases.services.log.case_log_mutation_service import CaseLogMutationService

        assert CaseLogMutationService is not None

    def test_case_log_query_service_importable(self) -> None:
        from apps.cases.services.log.case_log_query_service import CaseLogQueryService

        assert CaseLogQueryService is not None

    def test_email_folder_scan_service_importable(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService

        assert EmailFolderScanService is not None


# ── Number Services ─────────────────────────────────────────────────────────


class TestNumberServices:
    """cases/services/number/ tests."""

    def test_case_number_service_importable(self) -> None:
        from apps.cases.services.number.case_number_service import CaseNumberService

        assert CaseNumberService is not None

    def test_case_filing_number_service_importable(self) -> None:
        from apps.cases.services.number.case_filing_number_service import CaseFilingNumberService

        assert CaseFilingNumberService is not None


# ── Material Services ───────────────────────────────────────────────────────


class TestMaterialServices:
    """cases/services/material/ tests."""

    def test_case_material_service_importable(self) -> None:
        from apps.cases.services.material.case_material_service import CaseMaterialService

        assert CaseMaterialService is not None

    def test_case_material_query_service_importable(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        assert CaseMaterialQueryService is not None

    def test_folder_scan_service_importable(self) -> None:
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService

        assert CaseFolderScanService is not None


# ── Party Services ──────────────────────────────────────────────────────────


class TestPartyServices:
    """cases/services/party/ tests."""

    def test_case_assignment_service_importable(self) -> None:
        from apps.cases.services.party.case_assignment_service import CaseAssignmentService

        assert CaseAssignmentService is not None

    def test_case_party_service_importable(self) -> None:
        from apps.cases.services.party.case_party_service import CasePartyService

        assert CasePartyService is not None


# ── Template Services ───────────────────────────────────────────────────────


class TestTemplateServices:
    """cases/services/template/ tests."""

    def test_case_template_binding_service_importable(self) -> None:
        from apps.cases.services.template.case_template_binding_service import CaseTemplateBindingService

        assert CaseTemplateBindingService is not None

    def test_folder_binding_service_importable(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        assert CaseFolderBindingService is not None

    def test_unified_template_generation_service_importable(self) -> None:
        from apps.cases.services.template.unified_template_generation_service import UnifiedTemplateGenerationService

        assert UnifiedTemplateGenerationService is not None


# ── Chat Services ───────────────────────────────────────────────────────────


class TestChatServices:
    """cases/services/chat/ tests."""

    def test_case_chat_service_importable(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService

        assert CaseChatService is not None

    def test_chat_name_config_service_importable(self) -> None:
        from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService

        assert ChatNameConfigService is not None

    def test_recreate_policy_importable(self) -> None:
        from apps.cases.services.chat.recreate_policy import ChatRecreatePolicy

        assert ChatRecreatePolicy is not None

    def test_notification_usecase_importable(self) -> None:
        from apps.cases.services.chat.notification_usecase import SendNotificationUsecase

        assert SendNotificationUsecase is not None


# ── Data Services ───────────────────────────────────────────────────────────


class TestDataServices:
    """cases/services/data/ tests."""

    def test_cause_court_data_service_importable(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService

        assert CauseCourtDataService is not None

    def test_litigation_fee_calculator_service_importable(self) -> None:
        from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

        assert LitigationFeeCalculatorService is not None
