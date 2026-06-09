"""
Tests for apps.document_recognition.services — 文档识别服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestDocumentRecognitionModules:
    """文档识别模块可导入性测试"""

    def test_info_extractor_importable(self) -> None:
        from apps.document_recognition.services.info_extractor import InfoExtractor

        assert InfoExtractor is not None

    @pytest.mark.django_db
    def test_info_extractor_get_ollama_model(self) -> None:
        from apps.document_recognition.services.info_extractor import get_ollama_model

        # Should not raise
        model = get_ollama_model()
        assert isinstance(model, str)

    @pytest.mark.django_db
    def test_info_extractor_get_ollama_base_url(self) -> None:
        from apps.document_recognition.services.info_extractor import get_ollama_base_url

        url = get_ollama_base_url()
        assert isinstance(url, str)

    def test_recognition_service_importable(self) -> None:
        from apps.document_recognition.services import recognition_service

        assert recognition_service is not None

    def test_text_extraction_service_importable(self) -> None:
        from apps.document_recognition.services import text_extraction_service

        assert text_extraction_service is not None

    def test_case_binding_service_importable(self) -> None:
        from apps.document_recognition.services import case_binding_service

        assert case_binding_service is not None

    def test_notification_service_importable(self) -> None:
        from apps.document_recognition.services import notification_service

        assert notification_service is not None

    def test_task_service_importable(self) -> None:
        from apps.document_recognition.services import task_service

        assert task_service is not None

    def test_adapter_importable(self) -> None:
        from apps.document_recognition.services import adapter

        assert adapter is not None


# ============================================================
# InvoiceRecognition 测试
# ============================================================


class TestInvoiceRecognition:
    """发票识别服务测试"""

    def test_recognition_result_dataclass(self) -> None:
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        result = RecognitionResult(filename="test.pdf", success=True, data=None, error=None)
        assert result.filename == "test.pdf"
        assert result.success is True
        assert result.data is None
        assert result.error is None

    def test_recognition_result_failure(self) -> None:
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        result = RecognitionResult(filename="bad.pdf", success=False, error="OCR failed")
        assert result.success is False
        assert result.error == "OCR failed"

    def test_invoice_parser_importable(self) -> None:
        from apps.invoice_recognition.services import invoice_parser

        assert invoice_parser is not None

    def test_invoice_recognition_service_importable(self) -> None:
        from apps.invoice_recognition.services import invoice_recognition_service

        assert invoice_recognition_service is not None

    def test_quick_recognition_service_importable(self) -> None:
        from apps.invoice_recognition.services import quick_recognition_service

        assert quick_recognition_service is not None

    def test_invoice_download_service_importable(self) -> None:
        from apps.invoice_recognition.services import invoice_download_service

        assert invoice_download_service is not None


# ============================================================
# ChatRecords 测试
# ============================================================


class TestChatRecordsServices:
    """聊天记录服务测试"""

    def test_access_policy_importable(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        assert callable(ensure_can_access_project)

    def test_access_policy_admin_user(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        admin_user = MagicMock()
        admin_user.is_staff = True
        # Admin should not raise
        ensure_can_access_project(user=admin_user, project=MagicMock())

    def test_access_policy_no_user_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project
        from apps.core.exceptions import PermissionDenied

        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=None, project=MagicMock())

    def test_access_policy_anonymous_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project
        from apps.core.exceptions import PermissionDenied

        mock_user = MagicMock()
        mock_user.is_authenticated = False
        mock_user.is_admin = False
        mock_user.is_superuser = False
        mock_user.is_staff = False
        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=mock_user, project=MagicMock())

    def test_project_service_importable(self) -> None:
        from apps.chat_records.services.core import project_service

        assert project_service is not None

    def test_screenshot_service_importable(self) -> None:
        from apps.chat_records.services.core import screenshot_service

        assert screenshot_service is not None

    def test_export_service_importable(self) -> None:
        from apps.chat_records.services.export import export_service

        assert export_service is not None

    def test_docx_export_service_importable(self) -> None:
        from apps.chat_records.services.export import docx_export_service

        assert docx_export_service is not None


# ============================================================
# DocConverter 测试
# ============================================================


class TestDocConverterServices:
    """文档转换服务测试"""

    def test_converter_service_importable(self) -> None:
        from apps.doc_converter.services import converter_service

        assert converter_service is not None

    def test_engine_importable(self) -> None:
        from apps.doc_converter.services import engine

        assert engine is not None

    def test_storage_importable(self) -> None:
        from apps.doc_converter.services import storage

        assert storage is not None


# ============================================================
# MessageHub 测试
# ============================================================


class TestMessageHubServices:
    """消息中心服务测试"""

    def test_base_importable(self) -> None:
        from apps.message_hub.services import base

        assert base is not None

    def test_inbox_query_importable(self) -> None:
        from apps.message_hub.services import inbox_query

        assert inbox_query is not None

    def test_court_fetcher_importable(self) -> None:
        from apps.message_hub.services.court import court_fetcher

        assert court_fetcher is not None

    def test_court_schedule_fetcher_importable(self) -> None:
        from apps.message_hub.services.court import court_schedule_fetcher

        assert court_schedule_fetcher is not None

    def test_imap_fetcher_importable(self) -> None:
        from apps.message_hub.services.imap import imap_fetcher

        assert imap_fetcher is not None
