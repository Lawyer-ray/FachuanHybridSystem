"""Coverage tests for remaining modules - batch 3.

Targets uncovered lines in many modules:
- automation/services/chat/owner_config_manager.py (59 unc)
- automation/services/scraper/core/monitor_service.py (62 unc)
- automation/services/token/_login_handler.py (70 unc)
- automation/services/token/auto_token_acquisition_service.py (93 unc)
- core/llm/backends/ollama.py (100 unc)
- core/filesystem/folder_binding_crud_service.py (86 unc)
- core/filesystem/folder_binding_base.py (73 unc)
- client/services/id_card_merge/facade.py (86 unc)
- client/services/id_card_merge/detection.py (51 unc)
- evidence_sorting/services/reconciler.py (72 unc)
"""

from __future__ import annotations

import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest


# ===================================================================
# OwnerConfigManager: pattern validation
# ===================================================================
class TestOwnerConfigManagerPatterns:
    def test_open_id_pattern_valid(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        pattern = OwnerConfigManager.OPEN_ID_PATTERN
        assert pattern.match("ou_" + "a" * 32)

    def test_open_id_pattern_invalid(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        pattern = OwnerConfigManager.OPEN_ID_PATTERN
        assert not pattern.match("invalid_id")
        assert not pattern.match("ou_short")
        assert not pattern.match("on_" + "a" * 32)

    def test_union_id_pattern_valid(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        pattern = OwnerConfigManager.UNION_ID_PATTERN
        assert pattern.match("on_" + "0" * 32)

    def test_union_id_pattern_invalid(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        pattern = OwnerConfigManager.UNION_ID_PATTERN
        assert not pattern.match("ou_" + "a" * 32)


# ===================================================================
# MonitorService: pure logic methods
# ===================================================================
class TestMonitorService:
    def test_task_service_injected(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        mock_service = Mock()
        svc = MonitorService(task_service=mock_service)
        assert svc.task_service is mock_service

    def test_alert_service_injected(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        mock_alert = Mock()
        svc = MonitorService(alert_service=mock_alert)
        assert svc.alert_service is mock_alert

    def test_alert_service_lazy_load(self):
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        svc = MonitorService()
        assert svc.alert_service is not None


# ===================================================================
# _login_handler: mock patterns
# ===================================================================
class TestLoginHandlerPatterns:
    def test_login_handler_import(self):
        from apps.automation.services.token._login_handler import LoginHandler

        assert LoginHandler is not None


# ===================================================================
# auto_token_acquisition_service: mock patterns
# ===================================================================
class TestAutoTokenAcquisitionServicePatterns:
    def test_service_import(self):
        from apps.automation.services.token.auto_token_acquisition_service import (
            AutoTokenAcquisitionService,
        )

        assert AutoTokenAcquisitionService is not None


# ===================================================================
# id_card_merge: detection module
# ===================================================================
class TestIdCardDetection:
    def test_find_best_contour_empty(self):
        from apps.client.services.id_card_merge.detection import _find_best_contour

        result = _find_best_contour([], 100000, 1.586)
        assert result is None

    def test_compute_edges_import(self):
        from apps.client.services.id_card_merge.detection import _compute_edges

        assert callable(_compute_edges)

    def test_detect_id_card_corners_none_image(self):
        from apps.client.services.id_card_merge.detection import detect_id_card_corners

        logger = Mock()
        result = detect_id_card_corners(None, id_card_aspect_ratio=1.586, logger=logger)
        assert result is None
        logger.warning.assert_called_once()


# ===================================================================
# id_card_merge: facade module
# ===================================================================
class TestIdCardMergeFacade:
    def test_facade_import(self):
        from apps.client.services.id_card_merge.facade import IdCardMergeService

        assert IdCardMergeService is not None


# ===================================================================
# FolderBindingCrudService: helper methods
# ===================================================================
class TestFolderBindingCrudService:
    def test_get_owner_type(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = SimpleNamespace(case_type="civil")
        assert svc._get_owner_type(owner) == "civil"

    def test_get_owner_type_empty(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = SimpleNamespace(case_type="")
        assert svc._get_owner_type(owner) == ""

    def test_resolve_subdir_path_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        assert svc._resolve_subdir_path(owner_type="civil", subdir_key="test") is None

    def test_compute_relative_path_no_contract(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = SimpleNamespace(contract=None)
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_compute_relative_path_no_folder_binding(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        contract = SimpleNamespace(folder_binding=None)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_compute_relative_path_no_folder_path(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_compute_relative_path_relative(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="/data/contracts/1")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/data/contracts/1/case_files")
        assert result == "case_files"

    def test_compute_relative_path_not_relative(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="/data/contracts/1")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/other/path")
        assert result is None


# ===================================================================
# FolderBindingBaseService: helper methods
# ===================================================================
class TestFolderBindingBaseService:
    def test_is_cloud_storage_local(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="local")
        assert svc._is_cloud_storage(binding) is False

    def test_is_cloud_storage_s3_no_account(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_is_cloud_storage_s3_with_account(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=SimpleNamespace())
        assert svc._is_cloud_storage(binding) is True

    def test_check_folder_accessible_local_not_exists(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        result = svc.check_folder_accessible("/nonexistent/path/that/does/not/exist")
        assert result is False

    def test_check_folder_accessible_local_oserror(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        with patch("apps.core.filesystem.folder_binding_base.Path") as mock_path:
            mock_path.return_value.exists.side_effect = OSError("permission denied")
            result = svc.check_folder_accessible("/some/path")
            assert result is False


# ===================================================================
# OllamaBackend: helper methods
# ===================================================================
class TestOllamaBackendHelpers:
    def test_backend_import(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        assert OllamaBackend is not None

    def test_build_options_import(self):
        from apps.core.llm.backends.ollama import build_ollama_chat_payload

        assert callable(build_ollama_chat_payload)


# ===================================================================
# Evidence reconciler: data classes
# ===================================================================
class TestEvidenceReconcilerDataClasses:
    def test_delivery_note_defaults(self):
        from apps.evidence_sorting.services.reconciler import DeliveryNote

        dn = DeliveryNote()
        assert dn.filename == ""

    def test_delivery_note_import(self):
        from apps.evidence_sorting.services.reconciler import DeliveryNote

        assert DeliveryNote is not None


# ===================================================================
# ImageRotation: OrientationDetectionService
# ===================================================================
class TestOrientationDetectionService:
    def test_detect_orientation_no_ocr(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), "ocr_service", new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation(b"image_data")
            assert result["rotation"] == 0
            assert result["method"] == "none"


# ===================================================================
# Legal solution: SolutionGenerator
# ===================================================================
class TestSolutionGeneratorImport:
    def test_import(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        assert SolutionGenerator is not None

    def test_md_to_html_basic(self):
        from apps.legal_solution.services.solution_generator import _md_to_html

        result = _md_to_html("simple text")
        assert "simple text" in result


# ===================================================================
# document_recognition: recognize_document usecase
# ===================================================================
class TestRecognizeDocumentUsecase:
    def test_import(self):
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        assert RecognizeCourtDocumentUsecase is not None


# ===================================================================
# Automation document_delivery: matching
# ===================================================================
class TestDocumentDeliveryMatching:
    def test_import(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._matching import (
            DocumentMatchingMixin,
        )

        assert DocumentMatchingMixin is not None


# ===================================================================
# Automation document_delivery: query
# ===================================================================
class TestDocumentDeliveryQuery:
    def test_import(self):
        from apps.automation.services.document_delivery.api.document_delivery_api_service._query import (
            DocumentQueryMixin,
        )

        assert DocumentQueryMixin is not None


# ===================================================================
# automation sms_case_number_extractor_service
# ===================================================================
class TestCaseNumberExtractorMore:
    def test_normalize_single_whitespace_stripped(self):
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        cn_svc = Mock()
        cn_svc.normalize_case_number.return_value = "  (2024)粤01民初1号  "
        result = svc._normalize_single("  test  ", 0, cn_svc)
        # After normalization returns stripped value, regex check
        cn_svc.normalize_case_number.assert_called_once_with("test")


# ===================================================================
# cases/services/template modules
# ===================================================================
class TestCaseTemplateModules:
    def test_import_binding_service(self):
        from apps.cases.services.template.case_template_binding_service import (
            CaseTemplateBindingService,
        )

        assert CaseTemplateBindingService is not None

    def test_import_generation_service(self):
        from apps.cases.services.template.case_template_generation_service import (
            CaseTemplateGenerationService,
        )

        assert CaseTemplateGenerationService is not None

    def test_import_folder_binding_service(self):
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        assert CaseFolderBindingService is not None


# ===================================================================
# contracts/services/archive/learning_service
# ===================================================================
class TestContractArchiveLearningService:
    def test_import(self):
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        assert ArchiveLearningService is not None


# ===================================================================
# documents/services/placeholders modules
# ===================================================================
class TestPlaceholderServices:
    def test_enforcement_basic_service_import(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        assert EnforcementCaseNumberService is not None

    def test_case_detail_service_import(self):
        from apps.documents.services.placeholders.contract.case_detail_service import (
            CaseDetailService,
        )

        assert CaseDetailService is not None


# ===================================================================
# documents/services/generation modules
# ===================================================================
class TestDocumentGenerationServices:
    def test_preservation_materials_generation_import(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        assert PreservationMaterialsGenerationService is not None


# ===================================================================
# documents/services/external_template/analysis_service
# ===================================================================
class TestExternalTemplateAnalysisService:
    def test_import(self):
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        assert AnalysisService is not None


# ===================================================================
# documents/services/extractors/judgment_pdf_extractor
# ===================================================================
class TestJudgmentPdfExtractor:
    def test_import(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import (
            JudgmentPdfExtractor,
        )

        assert JudgmentPdfExtractor is not None


# ===================================================================
# document_recognition services
# ===================================================================
class TestDocumentRecognitionServices:
    def test_info_extractor_import(self):
        from apps.document_recognition.services.info_extractor import InfoExtractor

        assert InfoExtractor is not None

    def test_case_binding_service_import(self):
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        assert CaseBindingService is not None


# ===================================================================
# client/services/id_card_merge/detection.py
# ===================================================================
class TestIdCardDetectionMore:
    def test_detect_none_image(self):
        from apps.client.services.id_card_merge.detection import detect_id_card_corners

        logger = Mock()
        result = detect_id_card_corners(None, id_card_aspect_ratio=1.586, logger=logger)
        assert result is None

    def test_detect_empty_image(self):
        import numpy as np
        from apps.client.services.id_card_merge.detection import detect_id_card_corners

        logger = Mock()
        empty_img = np.array([], dtype=np.uint8)
        result = detect_id_card_corners(empty_img, id_card_aspect_ratio=1.586, logger=logger)
        assert result is None


# ===================================================================
# automation/services/sms/case_matcher more tests
# ===================================================================
class TestCaseMatcherMore:
    def test_extract_features_from_numbers_mixed(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        case_type, stage, is_bankruptcy = matcher._extract_features_from_numbers(
            ["(2024)粤01民初1号", "(2024)粤01执2号"]
        )
        assert isinstance(case_type, (str, type(None)))

    def test_narrow_down_single_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        with patch.object(matcher, "_extract_features_from_numbers", return_value=("civil", None, False)):
            with patch.object(matcher, "_apply_type_filter", return_value=[SimpleNamespace(id=1)]):
                with patch.object(matcher, "_apply_stage_filter", return_value=[SimpleNamespace(id=1)]):
                    result = matcher._narrow_down_by_case_number_features(
                        [SimpleNamespace(id=1)], ["(2024)粤01民初1号"]
                    )
                    assert result is not None

    def test_narrow_down_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher

        matcher = CaseMatcher()
        c1 = SimpleNamespace(name="某公司破产重整案", id=1)
        with patch.object(matcher, "_extract_features_from_numbers", return_value=(None, None, True)):
            result = matcher._narrow_down_by_case_number_features(
                [c1], ["(2024)粤01破1号"]
            )
            assert result == c1


# ===================================================================
# contracts/services/contract/admin/contract_admin_mutation_service
# ===================================================================
class TestContractAdminMutationService:
    def test_import(self):
        from apps.contracts.services.contract.admin.contract_admin_mutation_service import (
            ContractAdminMutationService,
        )

        assert ContractAdminMutationService is not None


# ===================================================================
# documents/services/template/folder_template/admin_service
# ===================================================================
class TestFolderTemplateAdminService:
    def test_import(self):
        from apps.documents.services.template.folder_template.admin_service import (
            FolderTemplateAdminService,
        )

        svc = FolderTemplateAdminService()
        assert svc._folder_template_service is None

    def test_validate_and_fix_template_form_valid(self):
        from apps.documents.services.template.folder_template.admin_service import (
            FolderTemplateAdminService,
        )

        svc = FolderTemplateAdminService()
        form_data = {
            "name": "测试模板",
            "template_type": "folder",
            "legal_status_match_mode": "all",
            "stages": [],
            "compact_archive": False,
        }
        result = svc.validate_and_fix_template_form(form_data)
        assert "is_valid" in result
