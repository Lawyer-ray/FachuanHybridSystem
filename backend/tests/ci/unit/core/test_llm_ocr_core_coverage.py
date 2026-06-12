"""Coverage tests for core LLM backends, OCR service, and related modules."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# --- ollama backend ---

class TestOllamaBackend:
    def test_init(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        assert backend is not None
        assert backend.BACKEND_NAME == "ollama"

    def test_init_with_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend(config=MagicMock())
        assert backend._config is not None


# --- openai_compatible backend ---

class TestOpenAICompatibleBackend:
    def test_init(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        assert backend is not None
        assert backend.BACKEND_NAME == "openai_compatible"

    def test_normalize_messages(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        messages = [{"role": "user", "content": "hello"}, {"role": "invalid", "content": "test"}]
        result = backend._normalize_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "user"

    def test_build_extra_body_thinking_disabled(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("kimi26")
        assert result is not None
        assert result["chat_template_kwargs"]["thinking"] is False

    def test_build_extra_body_normal(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("gpt-4")
        assert result is None


# --- OCR service ---

class TestOCRService:
    def test_init(self):
        from apps.automation.services.ocr.ocr_service import OCRService

        service = OCRService(use_v5=False, provider="local")
        assert service.use_v5 is False

    def test_ocr_text_result(self):
        from apps.automation.services.ocr.ocr_service import OCRTextResult

        result = OCRTextResult(text="hello", raw_texts=["hello"])
        assert result.text == "hello"
        assert result.raw_texts == ["hello"]


# --- PaddleOCR API service ---

class TestPaddleOCRApiService:
    def test_paddleocr_api_result(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiResult

        result = PaddleOCRApiResult(text="test", raw_texts=["test"], model="pp_ocrv5")
        assert result.text == "test"
        assert result.model == "pp_ocrv5"

    def test_engine_init(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        engine = PaddleOCRApiEngine(model="pp_ocrv5")
        assert engine._model == "pp_ocrv5"

    def test_engine_model_from_config(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService") as mock_config:
            mock_config.return_value.get_value.return_value = "paddleocr_vl"
            engine = PaddleOCRApiEngine()
            assert engine.model == "paddleocr_vl"

    def test_looks_like_json_noise_true(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)
        assert engine._looks_like_json_noise('{"key": "value", "another": "data"}') is True

    def test_looks_like_json_noise_false(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        engine = PaddleOCRApiEngine.__new__(PaddleOCRApiEngine)
        assert engine._looks_like_json_noise("这是正常文字") is False
        assert engine._looks_like_json_noise("ab") is False


# --- storage_service ---

class TestStorageService:
    def test_import(self):
        from apps.core.services.storage_service import FileValidator

        assert FileValidator is not None


# --- material_classification_service ---

class TestMaterialClassificationService:
    def test_import(self):
        from apps.core.services.material_classification_service import MaterialClassificationService

        assert MaterialClassificationService is not None


# --- cause_court_initialization_service ---

class TestCauseCourtInitializationService:
    def test_import(self):
        from apps.core.services.cause_court_initialization_service import CauseCourtInitializationService

        assert CauseCourtInitializationService is not None


# --- bound_folder_scan_service ---

class TestBoundFolderScanService:
    def test_import(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService is not None


# --- court_api_client ---

class TestCourtApiClient:
    def test_import(self):
        from apps.core.services.court_api_client import CourtApiClient

        assert CourtApiClient is not None


# --- automation factory ---

class TestAutomationFactory:
    def test_import(self):
        from apps.core.exceptions.automation_factory import AutomationExceptions

        assert AutomationExceptions is not None


# --- gdrive_provider ---

class TestGDriveProvider:
    def test_import(self):
        from apps.core.cloud_storage.gdrive_provider import GDriveProvider

        assert GDriveProvider is not None


# --- dropbox_provider ---

class TestDropboxProvider:
    def test_import(self):
        from apps.core.cloud_storage.dropbox_provider import DropboxProvider

        assert DropboxProvider is not None


# --- cloud_storage admin ---

class TestCloudStorageAdmin:
    def test_import(self):
        from apps.core.cloud_storage.admin import CloudStorageAccountAdmin

        assert CloudStorageAccountAdmin is not None


# --- folder_binding_base ---

class TestFolderBindingBase:
    def test_import(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        assert BaseFolderBindingService is not None


# --- core admin models ---

class TestTianyanchaResponseAdapter:
    def test_import(self):
        from apps.enterprise_data.services.providers.adapters.tianyancha_response_adapter import TianyanchaResponseAdapter

        assert TianyanchaResponseAdapter is not None
