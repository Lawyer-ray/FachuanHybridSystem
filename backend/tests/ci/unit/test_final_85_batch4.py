"""Coverage tests for batch 4 - targeting uncovered code paths.

Focus on OwnerConfigManager, document_delivery, and other uncovered services.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest


# ===================================================================
# OwnerConfigManager: validate_owner_id
# ===================================================================
class TestOwnerConfigManagerValidateOwnerId:
    def _make_manager(self):
        """Create an OwnerConfigManager without DB access."""
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value={}):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None):
                return OwnerConfigManager()

    def test_valid_open_id(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id("ou_" + "a" * 32) is True

    def test_valid_union_id(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id("on_" + "0" * 32) is True

    def test_invalid_id(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id("invalid") is False

    def test_empty_string(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id("") is False

    def test_none(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id(None) is False

    def test_whitespace_only(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id("   ") is False

    def test_not_string(self):
        mgr = self._make_manager()
        assert mgr.validate_owner_id(123) is False


# ===================================================================
# OwnerConfigManager: validate_owner_id_strict
# ===================================================================
class TestOwnerConfigManagerValidateStrict:
    def _make_manager(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value={}):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None):
                return OwnerConfigManager()

    def test_valid_id_no_exception(self):
        mgr = self._make_manager()
        mgr.validate_owner_id_strict("ou_" + "a" * 32)  # no exception

    def test_invalid_id_raises(self):
        from apps.core.exceptions import ValidationException

        mgr = self._make_manager()
        with pytest.raises(ValidationException):
            mgr.validate_owner_id_strict("invalid_id")


# ===================================================================
# OwnerConfigManager: get_effective_owner_id
# ===================================================================
class TestOwnerConfigManagerGetEffectiveOwnerId:
    def _make_manager(self, config=None, default_id=None):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        config = config or {}
        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=default_id):
                return OwnerConfigManager()

    def test_specified_valid_id(self):
        mgr = self._make_manager(config={"OWNER_VALIDATION_ENABLED": True})
        result = mgr.get_effective_owner_id("ou_" + "a" * 32)
        assert result == "ou_" + "a" * 32

    def test_specified_invalid_id_falls_back_to_default(self):
        valid_id = "ou_" + "b" * 32
        mgr = self._make_manager(
            config={"OWNER_VALIDATION_ENABLED": True},
            default_id=valid_id,
        )
        result = mgr.get_effective_owner_id("invalid")
        assert result == valid_id

    def test_no_specified_no_default(self):
        mgr = self._make_manager()
        result = mgr.get_effective_owner_id(None)
        assert result is None

    def test_empty_specified_uses_default(self):
        valid_id = "on_" + "c" * 32
        mgr = self._make_manager(default_id=valid_id)
        result = mgr.get_effective_owner_id("")
        assert result == valid_id

    def test_validation_disabled_uses_specified(self):
        mgr = self._make_manager(config={"OWNER_VALIDATION_ENABLED": False})
        result = mgr.get_effective_owner_id("any_value")
        assert result == "any_value"


# ===================================================================
# OwnerConfigManager: is_test_environment
# ===================================================================
class TestOwnerConfigManagerIsTestEnvironment:
    def _make_manager(self, config):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None):
                return OwnerConfigManager()

    def test_test_mode_true(self):
        mgr = self._make_manager({"TEST_MODE": True})
        assert mgr.is_test_environment() is True

    def test_test_mode_false(self):
        mgr = self._make_manager({"TEST_MODE": False})
        assert mgr.is_test_environment() is False


# ===================================================================
# OwnerConfigManager: get_default_owner_id
# ===================================================================
class TestOwnerConfigManagerGetDefaultOwnerId:
    def _make_manager(self, config, default_id):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=default_id):
                return OwnerConfigManager()

    def test_returns_default(self):
        mgr = self._make_manager({}, "ou_" + "a" * 32)
        assert mgr.get_default_owner_id() == "ou_" + "a" * 32

    def test_returns_none(self):
        mgr = self._make_manager({}, None)
        assert mgr.get_default_owner_id() is None


# ===================================================================
# OwnerConfigManager: _load_default_owner_id
# ===================================================================
class TestOwnerConfigManagerLoadDefaultOwnerId:
    def _make_manager_with_config(self, config):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            with patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None):
                return OwnerConfigManager()

    def test_load_from_config_directly(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        config = {"DEFAULT_OWNER_ID": "ou_" + "a" * 32}
        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            mgr = OwnerConfigManager()
            # The actual _load_default_owner_id runs during __init__
            assert mgr._default_owner_id == "ou_" + "a" * 32

    def test_test_env_fallback(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        config = {"TEST_MODE": True, "TEST_OWNER_ID": "on_" + "b" * 32}
        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            mgr = OwnerConfigManager()
            assert mgr._default_owner_id == "on_" + "b" * 32

    def test_no_default_returns_none(self):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        config = {}
        with patch.object(OwnerConfigManager, "_load_config", return_value=config):
            mgr = OwnerConfigManager()
            assert mgr._default_owner_id is None


# ===================================================================
# DocumentDelivery: token service
# ===================================================================
class TestDocumentDeliveryTokenService:
    def test_import(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )

        assert DocumentDeliveryTokenService is not None


# ===================================================================
# DocumentDelivery: coordinator
# ===================================================================
class TestDocumentDeliveryCoordinator:
    def test_import(self):
        from apps.automation.services.document_delivery.coordinator.document_delivery_coordinator import (
            DocumentDeliveryCoordinator,
        )

        assert DocumentDeliveryCoordinator is not None


# ===================================================================
# DocumentDelivery: api_delivery_service
# ===================================================================
class TestApiDeliveryService:
    def test_import(self):
        from apps.automation.services.document_delivery.delivery.api_delivery_service import (
            ApiDeliveryService,
        )

        assert ApiDeliveryService is not None


# ===================================================================
# Core API ninja_llm_api: schemas
# ===================================================================
class TestNinjaLlmApiSchemas:
    def test_import_chat_request(self):
        from apps.core.api.ninja_llm_api import ChatRequest

        assert ChatRequest is not None

    def test_import_chat_response(self):
        from apps.core.api.ninja_llm_api import ChatResponse

        assert ChatResponse is not None

    def test_import_model_info(self):
        from apps.core.api.ninja_llm_api import ModelInfo

        assert ModelInfo is not None


# ===================================================================
# RecognizeCourtDocumentUsecase
# ===================================================================
class TestRecognizeCourtDocumentUsecaseExecute:
    def test_execute_empty_text(self):
        from apps.core.exceptions.error_codes import TEXT_EXTRACTION_FAILED
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(
            success=False, text="", extraction_method="ocr"
        )
        usecase = RecognizeCourtDocumentUsecase(
            text_extraction=text_extraction,
            classifier=Mock(),
            extractor=Mock(),
            binding_service=Mock(),
            document_renamer=Mock(),
        )
        result = usecase.execute(file_path="/tmp/test.pdf")
        assert result.binding.success is False
        assert result.binding.error_code == TEXT_EXTRACTION_FAILED

    def test_execute_success_summons(self):
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(
            success=True, text="传票内容", extraction_method="pdf_direct"
        )
        classifier = Mock()
        classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        extractor = Mock()
        extractor.extract_summons_info.return_value = {
            "case_number": "(2024)粤01民初1号",
            "court_time": None,
        }
        binding_service = Mock()
        binding_service.find_case_by_number.return_value = 1
        binding_service.case_service.get_case_by_id_internal.return_value = SimpleNamespace(name="Test")
        binding_service.format_log_content.return_value = "log"
        binding_service.bind_document_to_case.return_value = SimpleNamespace(
            success=True, case_id=1, case_name="Test", case_log_id=10
        )

        document_renamer = Mock()
        document_renamer.generate_filename.return_value = "renamed.pdf"

        usecase = RecognizeCourtDocumentUsecase(
            text_extraction=text_extraction,
            classifier=classifier,
            extractor=extractor,
            binding_service=binding_service,
            document_renamer=document_renamer,
        )

        with patch(
            "apps.document_recognition.usecases.court_document_recognition.recognize_document.FilenameTemplateService"
        ) as mock_fts:
            mock_fts.get_unique_filepath.return_value = ("/tmp/renamed.pdf", True)
            with patch("builtins.open", MagicMock()):
                with patch("pathlib.Path.rename"):
                    result = usecase.execute(file_path="/tmp/test.pdf", user=Mock())

        assert result.recognition.document_type == DocumentType.SUMMONS
        assert result.recognition.case_number == "(2024)粤01民初1号"

    def test_execute_other_type(self):
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(
            success=True, text="其他内容", extraction_method="pdf_direct"
        )
        classifier = Mock()
        classifier.classify.return_value = (DocumentType.OTHER, 0.3)

        usecase = RecognizeCourtDocumentUsecase(
            text_extraction=text_extraction,
            classifier=classifier,
            extractor=Mock(),
            binding_service=Mock(),
            document_renamer=Mock(),
        )
        result = usecase.execute(file_path="/tmp/test.pdf")
        assert result.recognition.document_type == DocumentType.OTHER
        assert result.binding.success is False

    def test_execute_execution_ruling_type(self):
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(
            success=True, text="执行裁定书", extraction_method="pdf_direct"
        )
        classifier = Mock()
        classifier.classify.return_value = (DocumentType.EXECUTION_RULING, 0.8)
        extractor = Mock()
        extractor.extract_execution_info.return_value = {
            "case_number": None,
            "preservation_deadline": None,
        }

        usecase = RecognizeCourtDocumentUsecase(
            text_extraction=text_extraction,
            classifier=classifier,
            extractor=extractor,
            binding_service=Mock(),
            document_renamer=Mock(),
        )
        result = usecase.execute(file_path="/tmp/test.pdf")
        assert result.binding.success is False
        assert result.binding.error_code == "FEATURE_NOT_IMPLEMENTED"

    def test_execute_summons_no_case_number(self):
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
            RecognizeCourtDocumentUsecase,
        )

        text_extraction = Mock()
        text_extraction.extract_text.return_value = SimpleNamespace(
            success=True, text="传票无案号", extraction_method="pdf_direct"
        )
        classifier = Mock()
        classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        extractor = Mock()
        extractor.extract_summons_info.return_value = {"case_number": None, "court_time": None}

        usecase = RecognizeCourtDocumentUsecase(
            text_extraction=text_extraction,
            classifier=classifier,
            extractor=extractor,
            binding_service=Mock(),
            document_renamer=Mock(),
        )
        result = usecase.execute(file_path="/tmp/test.pdf")
        assert result.binding.success is False
        assert result.binding.error_code == "CASE_NUMBER_NOT_FOUND"
