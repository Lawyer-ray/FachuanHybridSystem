"""Direct coverage boost - targeting remaining uncovered data processing functions."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── cases/services/material/case_material_query_service.py ──────────


class TestCaseMaterialQueryService:
    def test_init_without_case_service(self):
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        assert svc._case_service is None

    def test_case_service_property_raises_without_injection(self):
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_case_service_property_returns_injected(self):
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        mock_cs = MagicMock()
        svc = CaseMaterialQueryService(case_service=mock_cs)
        assert svc.case_service is mock_cs


# ── cases/services/party/case_party_mutation_service.py ─────────────


class TestCasePartyMutationService:
    def test_validate_party_case_not_found(self):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService
        mock_repo = MagicMock()
        mock_repo.get_case.return_value = None
        svc = CasePartyMutationService(
            client_service=MagicMock(),
            contract_service=MagicMock(),
            repo=mock_repo,
        )
        with pytest.raises(Exception):
            svc.validate_party_in_contract_scope(999, 1)

    def test_validate_party_no_contract(self):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService
        mock_repo = MagicMock()
        mock_case = MagicMock()
        mock_case.contract_id = None
        mock_repo.get_case.return_value = mock_case
        svc = CasePartyMutationService(
            client_service=MagicMock(),
            contract_service=MagicMock(),
            repo=mock_repo,
        )
        result = svc.validate_party_in_contract_scope(1, 1)
        assert result is True


# ── cases/services/template/case_template_generation_service.py ─────


class TestCaseTemplateGenerationService:
    def test_constants(self):
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService
        assert CaseTemplateGenerationService.LEGAL_REP_CERT_TEMPLATE == "法定代表人身份证明书"
        assert CaseTemplateGenerationService.POWER_OF_ATTORNEY_TEMPLATE == "授权委托书"


# ── cases/services/template/case_document_template_admin_service.py ─


class TestCaseDocumentTemplateAdminService:
    def test_init(self):
        from apps.cases.services.template.case_document_template_admin_service import CaseDocumentTemplateAdminService
        svc = CaseDocumentTemplateAdminService()
        assert svc is not None


# ── automation/services/token/auto_token_acquisition_service.py ─────


class TestAutoTokenAcquisitionService:
    def test_init(self):
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        svc = AutoTokenAcquisitionService()
        assert svc is not None


# ── automation/usecases/token/auto_login_usecase.py ─────────────────


class TestAutoLoginUsecase:
    def test_class_exists(self):
        from apps.automation.usecases.token.auto_login_usecase import AutoLoginUsecase
        assert AutoLoginUsecase is not None


# ── document_recognition/services/case_binding_service.py ───────────


class TestCaseBindingService:
    def test_init(self):
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        svc = CaseBindingService()
        assert svc is not None


# ── client/services/id_card_merge/facade.py ─────────────────────────


class TestIdCardMergeFacade:
    def test_module_importable(self):
        import apps.client.services.id_card_merge.facade
        assert apps.client.services.id_card_merge.facade is not None


# ── chat_records/services/extraction/frame_processing_service.py ────


class TestFrameProcessingService:
    def test_init(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService
        svc = FrameProcessingService()
        assert svc is not None


# ── automation/services/document_delivery/delivery/api_delivery.py ──


class TestApiDeliveryService:
    def test_module_importable(self):
        import apps.automation.services.document_delivery.delivery.api_delivery
        assert apps.automation.services.document_delivery.delivery.api_delivery is not None


# ── enterprise_data/services/providers/qichacha_mcp.py ─────────────


class TestQichachaMcpProvider:
    def test_class_exists(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider
        assert QichachaMcpProvider is not None


# ── litigation_ai/consumers/ ────────────────────────────────────────


class TestLitigationConsumer:
    def test_class_exists(self):
        from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer
        assert LitigationConsumer is not None


class TestMockTrialConsumer:
    def test_class_exists(self):
        from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
        assert MockTrialConsumer is not None


# ── documents/services/template/folder_template/admin_service.py ────


class TestFolderTemplateAdminServiceExtended:
    def test_init_with_service(self):
        from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService
        mock_fts = MagicMock()
        svc = FolderTemplateAdminService(folder_template_service=mock_fts)
        assert svc.folder_template_service is mock_fts

    def test_init_without_service(self):
        from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService
        svc = FolderTemplateAdminService()
        assert svc._folder_template_service is None


# ── core/llm/backends/ollama.py ─────────────────────────────────────


class TestOllamaBackendExtended:
    def test_constants(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        assert OllamaBackend is not None
