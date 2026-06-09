"""Tests for cases services coverage boost - focusing on admin, chat, party, template, number services."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Case Admin Service Extended ─────────────────────────────────────────────


class TestCaseAdminServiceMoreMethods:
    """More case_admin_service.py method tests."""

    def _make_service(self) -> Any:
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_service = MagicMock()
        filing_service = MagicMock()
        return CaseAdminService(
            document_service=doc_service, filing_number_service=filing_service
        ), doc_service, filing_service

    def test_get_matched_case_file_templates(self) -> None:
        service, doc_service, _ = self._make_service()
        doc_service.find_matching_case_file_templates.return_value = [{"name": "起诉状"}]
        result = service.get_matched_case_file_templates("civil", "first_trial")
        assert isinstance(result, list)

    def test_get_matched_case_file_templates_exception(self) -> None:
        service, doc_service, _ = self._make_service()
        doc_service.find_matching_case_file_templates.side_effect = Exception("fail")
        result = service.get_matched_case_file_templates("civil", "first_trial")
        assert result == []

    def test_get_case_file_templates_for_detail_no_type(self) -> None:
        service, _, _ = self._make_service()
        case = MagicMock()
        case.case_type = None
        templates, reason = service.get_case_file_templates_for_detail(case)
        assert templates == []
        assert reason != ""

    def test_get_case_file_templates_for_detail_no_stage(self) -> None:
        service, _, _ = self._make_service()
        case = MagicMock()
        case.case_type = "civil"
        case.current_stage = None
        templates, reason = service.get_case_file_templates_for_detail(case)
        assert templates == []

    def test_filing_number_service_lazy(self) -> None:
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService(filing_number_service="test_filing")
        assert svc.filing_number_service == "test_filing"

    def test_document_service_lazy(self) -> None:
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService(document_service="test_doc")
        assert svc.document_service == "test_doc"


# ── Case Chat Service Extended ──────────────────────────────────────────────


class TestCaseChatServiceMoreMethods:
    """More case_chat_service.py tests."""

    def _make_service(self) -> Any:
        from apps.cases.services.chat.case_chat_service import CaseChatService

        repo = MagicMock()
        name_builder = MagicMock()
        provider_facade = MagicMock()
        recreate_policy = MagicMock()
        access_policy = MagicMock()
        return CaseChatService(
            repo=repo,
            name_builder=name_builder,
            provider_facade=provider_facade,
            recreate_policy=recreate_policy,
            access_policy=access_policy,
        ), repo, name_builder, provider_facade, recreate_policy, access_policy

    def test_init_defaults(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        assert svc.repo is not None
        assert svc.name_builder is not None

    def test_access_policy_lazy_init(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService(access_policy=None)
        policy = svc.access_policy
        assert policy is not None


# ── Chat Name Config Service ───────────────────────────────────────────────


class TestChatNameConfigServiceExtended:
    """chat_name_config_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService

        assert ChatNameConfigService is not None

    @pytest.mark.django_db
    def test_default_render(self) -> None:
        from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService

        svc = ChatNameConfigService()
        result = svc.render_chat_name(case_name="测试案件", stage="一审", case_type="民事")
        assert isinstance(result, str)


# ── Case Assignment Service ─────────────────────────────────────────────────


class TestCaseAssignmentServiceExtended:
    """case_assignment_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.party.case_assignment_service import CaseAssignmentService

        assert CaseAssignmentService is not None

    def test_init(self) -> None:
        from apps.cases.services.party.case_assignment_service import CaseAssignmentService

        svc = CaseAssignmentService()
        assert svc is not None


# ── Case Party Mutation Service ─────────────────────────────────────────────


class TestCasePartyMutationServiceExtended:
    """case_party_mutation_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        assert CasePartyMutationService is not None


# ── Case Party Query Facade ─────────────────────────────────────────────────


class TestCasePartyQueryFacadeExtended:
    """case_party_query_facade.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.party.case_party_query_facade import CasePartyQueryFacade

        assert CasePartyQueryFacade is not None


# ── Case Number Service ─────────────────────────────────────────────────────


class TestCaseNumberServiceExtended:
    """case_number_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.number.case_number_service import CaseNumberService

        assert CaseNumberService is not None

    def test_init(self) -> None:
        from apps.cases.services.number.case_number_service import CaseNumberService

        svc = CaseNumberService()
        assert svc is not None


# ── Case Filing Number Service ──────────────────────────────────────────────


class TestCaseFilingNumberServiceExtended:
    """case_filing_number_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.number.case_filing_number_service import CaseFilingNumberService

        assert CaseFilingNumberService is not None


# ── Case Material Service ───────────────────────────────────────────────────


class TestCaseMaterialServiceExtended:
    """case_material_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.material.case_material_service import CaseMaterialService

        assert CaseMaterialService is not None

    def test_init_requires_case_service(self) -> None:
        from apps.cases.services.material.case_material_service import CaseMaterialService

        with pytest.raises(RuntimeError, match="case_service"):
            CaseMaterialService(case_service=None)

    def test_init_with_case_service(self) -> None:
        from apps.cases.services.material.case_material_service import CaseMaterialService

        mock_case_svc = MagicMock()
        svc = CaseMaterialService(case_service=mock_case_svc)
        assert svc is not None


# ── Case Material Binding Workflow ──────────────────────────────────────────


class TestCaseMaterialBindingWorkflow:
    """case_material_binding_workflow.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.material.case_material_binding_workflow import CaseMaterialBindingWorkflow

        assert CaseMaterialBindingWorkflow is not None


# ── Case Material Query Service ─────────────────────────────────────────────


class TestCaseMaterialQueryServiceExtended:
    """case_material_query_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        assert CaseMaterialQueryService is not None


# ── Email Folder Scan Service ───────────────────────────────────────────────


class TestEmailFolderScanServiceExtended:
    """email_folder_scan_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService

        assert EmailFolderScanService is not None


# ── Case Template Binding Service ───────────────────────────────────────────


class TestCaseTemplateBindingServiceExtended:
    """case_template_binding_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.case_template_binding_service import CaseTemplateBindingService

        assert CaseTemplateBindingService is not None


# ── Case Template Generation Service ────────────────────────────────────────


class TestCaseTemplateGenerationServiceExtended:
    """case_template_generation_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        assert CaseTemplateGenerationService is not None


# ── Case Document Template Admin Service ────────────────────────────────────


class TestCaseDocumentTemplateAdminService:
    """case_document_template_admin_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.case_document_template_admin_service import CaseDocumentTemplateAdminService

        assert CaseDocumentTemplateAdminService is not None


# ── Folder Binding Service ──────────────────────────────────────────────────


class TestFolderBindingServiceExtended:
    """folder_binding_service.py (template) tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        assert CaseFolderBindingService is not None


# ── Case Access Service ─────────────────────────────────────────────────────


class TestCaseAccessServiceExtended:
    """case_access_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        assert CaseAccessService is not None


# ── Case Command Service Extended ───────────────────────────────────────────


class TestCaseCommandServiceCreateCtx:
    """case_command_service.py AccessContext variant tests."""

    @pytest.mark.django_db
    def test_create_case_ctx(self) -> None:
        from apps.cases.services.case.case_command_service import CaseCommandService
        from apps.core.security.access_context import AccessContext
        from apps.contracts.models import Contract

        svc = CaseCommandService(contract_service=None, access_policy=MagicMock())
        contract = Contract.objects.create(name="ctx合同", case_type="civil")
        ctx = AccessContext(user=MagicMock(), org_access=None, perm_open_access=True)
        case = svc.create_case_ctx(data={"name": "ctx案件", "contract": contract}, ctx=ctx)
        assert case.name == "ctx案件"

    @pytest.mark.django_db
    def test_update_case_not_found(self) -> None:
        from apps.cases.services.case.case_command_service import CaseCommandService
        from apps.core.exceptions import NotFoundError

        svc = CaseCommandService(contract_service=None, access_policy=MagicMock())
        with pytest.raises(NotFoundError):
            svc.update_case(999999, {"name": "不存在"}, user=None, perm_open_access=True)


# ── Cause Court Data Service ────────────────────────────────────────────────


class TestCauseCourtDataServiceExtended:
    """cause_court_data_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService

        assert CauseCourtDataService is not None


# ── Litigation Fee Calculator Service ───────────────────────────────────────


class TestLitigationFeeCalculatorServiceExtended:
    """litigation_fee_calculator_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

        assert LitigationFeeCalculatorService is not None

    def test_init(self) -> None:
        from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

        svc = LitigationFeeCalculatorService()
        assert svc is not None


# ── Cause Rule Service ──────────────────────────────────────────────────────


class TestCauseRuleServiceExtended:
    """cause_rule_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.data.cause_rule_service import CauseRuleService

        assert CauseRuleService is not None


# ── Unified Template Generation Service ─────────────────────────────────────


class TestUnifiedTemplateGenerationServiceExtended:
    """unified_template_generation_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.template.unified_template_generation_service import UnifiedTemplateGenerationService

        assert UnifiedTemplateGenerationService is not None


# ── Case Internal Query Service ─────────────────────────────────────────────


class TestCaseInternalQueryServiceExtended:
    """case_internal_query_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService

        assert CaseInternalQueryService is not None


# ── Case Details Query Service ──────────────────────────────────────────────


class TestCaseDetailsQueryServiceExtended:
    """case_details_query_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_details_query_service import CaseDetailsQueryService

        assert CaseDetailsQueryService is not None


# ── Case Log Internal Service ───────────────────────────────────────────────


class TestCaseLogInternalServiceExtended:
    """case_log_internal_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_log_internal_service import CaseLogInternalService

        assert CaseLogInternalService is not None


# ── Case Export Serializer Service ──────────────────────────────────────────


class TestCaseExportSerializerService:
    """case_export_serializer_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case import case_export_serializer_service

        assert hasattr(case_export_serializer_service, "_serialize_client")


# ── Case Search Service Adapter ─────────────────────────────────────────────


class TestCaseSearchServiceAdapterExtended:
    """case_search_service_adapter.py tests."""

    def test_module_importable(self) -> None:
        from apps.cases.services.case.case_search_service_adapter import CaseSearchServiceAdapter

        assert CaseSearchServiceAdapter is not None


# ── Sync Case Assignments Command ───────────────────────────────────────────


class TestSyncCaseAssignmentsCommand:
    """sync_case_assignments_from_contracts.py management command tests."""

    def test_module_importable(self) -> None:
        from apps.cases.management.commands.sync_case_assignments_from_contracts import Command

        assert Command is not None
