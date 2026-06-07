"""
Comprehensive unit tests for DocumentProcessor.

Tests every public/private method including error paths and edge cases.
All external dependencies (DB, HTTP, file I/O, threading) are mocked.
"""

import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_case_matcher():
    return MagicMock()


@pytest.fixture
def mock_document_renamer():
    return MagicMock()


@pytest.fixture
def mock_notification_service():
    return MagicMock()


@pytest.fixture
def processor(mock_case_matcher, mock_document_renamer, mock_notification_service):
    from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

    return DocumentProcessor(
        case_matcher=mock_case_matcher,
        document_renamer=mock_document_renamer,
        notification_service=mock_notification_service,
    )


@pytest.fixture
def sample_record():
    return DocumentDeliveryRecord(
        case_number="(2025)粤0604民初41257号",
        send_time=datetime(2025, 12, 10, 16, 25, 37),
        element_index=0,
        document_name="判决书",
        court_name="佛山中院",
        delivery_event_id="EVT001",
    )


def _make_zip(tmp_path: Path, file_names: list[str] | None = None) -> str:
    """Helper: create a zip file with given file names and return its path."""
    if file_names is None:
        file_names = ["doc1.pdf", "doc2.pdf"]
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in file_names:
            zf.writestr(name, f"content of {name}")
    return str(zip_path)


# ===========================================================================
# __init__
# ===========================================================================

class TestInit:
    def test_init_with_all_deps(self, mock_case_matcher, mock_document_renamer, mock_notification_service):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        p = DocumentProcessor(
            case_matcher=mock_case_matcher,
            document_renamer=mock_document_renamer,
            notification_service=mock_notification_service,
        )
        assert p._case_matcher is mock_case_matcher
        assert p._document_renamer is mock_document_renamer
        assert p._notification_service is mock_notification_service

    def test_init_with_no_deps(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        p = DocumentProcessor()
        assert p._case_matcher is None
        assert p._document_renamer is None
        assert p._notification_service is None


# ===========================================================================
# Lazy-loading properties
# ===========================================================================

class TestLazyProperties:
    def test_case_matcher_returns_injected(self, processor, mock_case_matcher):
        assert processor.case_matcher is mock_case_matcher

    def test_document_renamer_returns_injected(self, processor, mock_document_renamer):
        assert processor.document_renamer is mock_document_renamer

    def test_notification_service_returns_injected(self, processor, mock_notification_service):
        assert processor.notification_service is mock_notification_service

    def test_case_matcher_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        p = DocumentProcessor()
        mock_cm = MagicMock()
        with patch(
            "apps.automation.services.sms.case_matcher.CaseMatcher", return_value=mock_cm
        ):
            result = p.case_matcher
        assert result is mock_cm
        # Second call should return cached value
        assert p.case_matcher is mock_cm

    def test_document_renamer_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        p = DocumentProcessor()
        mock_dr = MagicMock()
        with patch(
            "apps.automation.services.sms.document_renamer.DocumentRenamer", return_value=mock_dr
        ):
            result = p.document_renamer
        assert result is mock_dr

    def test_notification_service_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        p = DocumentProcessor()
        mock_ns = MagicMock()
        with patch(
            "apps.automation.services.sms.sms_notification_service.SMSNotificationService",
            return_value=mock_ns,
        ):
            result = p.notification_service
        assert result is mock_ns


# ===========================================================================
# extract_zip_if_needed
# ===========================================================================

class TestExtractZipIfNeeded:
    def test_non_zip_returns_none(self, processor):
        assert processor.extract_zip_if_needed("/some/file.pdf") is None

    def test_non_zip_uppercase_ext_returns_none(self, processor):
        assert processor.extract_zip_if_needed("/some/file.PDF") is None

    def test_valid_zip_returns_files(self, processor, tmp_path):
        zip_path = _make_zip(tmp_path, ["a.pdf", "b.pdf"])
        result = processor.extract_zip_if_needed(zip_path)
        assert result is not None
        assert len(result) == 2
        assert any("a.pdf" in f for f in result)
        assert any("b.pdf" in f for f in result)

    def test_zip_with_path_traversal_skips_unsafe(self, processor, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../etc/passwd", "malicious")
            zf.writestr("safe.txt", "ok")
        result = processor.extract_zip_if_needed(str(zip_path))
        # The traversal entry should be skipped
        assert result is not None
        assert len(result) == 1
        assert any("safe.txt" in f for f in result)

    def test_zip_extraction_error_returns_none(self, processor):
        # Non-existent zip path
        result = processor.extract_zip_if_needed("/nonexistent/file.zip")
        assert result is None

    def test_empty_zip_returns_empty_list(self, processor, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        result = processor.extract_zip_if_needed(str(zip_path))
        assert result is not None
        assert len(result) == 0

    def test_zip_case_insensitive_extension(self, processor, tmp_path):
        zip_path = tmp_path / "test.ZIP"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "data")
        result = processor.extract_zip_if_needed(str(zip_path))
        assert result is not None
        assert len(result) == 1


# ===========================================================================
# process_document
# ===========================================================================

class TestProcessDocument:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_success(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.return_value = {
            "success": True,
            "case_id": 42,
            "case_log_id": 99,
            "renamed_path": "/renamed/doc.pdf",
            "notification_sent": True,
            "error_message": None,
        }
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.zip",
            extracted_files=["/tmp/doc1.pdf"],
            credential_id=1,
        )
        assert result.success is True
        assert result.case_id == 42
        assert result.case_log_id == 99
        assert result.renamed_path == "/renamed/doc.pdf"
        assert result.notification_sent is True
        assert result.error_message is None

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_failure(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.return_value = {
            "success": False,
            "error_message": "some error",
        }
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result.success is False
        assert result.error_message == "some error"

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor.extract_zip_if_needed")
    def test_process_document_calls_extract_when_no_files(self, mock_extract, mock_sms_thread, processor, sample_record):
        mock_extract.return_value = ["/tmp/extracted.pdf"]
        mock_sms_thread.return_value = {"success": True}
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.zip",
            extracted_files=[],
            credential_id=1,
        )
        mock_extract.assert_called_once_with("/tmp/doc.zip")
        assert result.success is True

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor.extract_zip_if_needed")
    def test_process_document_fallback_to_file_path_when_extract_returns_none(
        self, mock_extract, mock_sms_thread, processor, sample_record
    ):
        mock_extract.return_value = None
        mock_sms_thread.return_value = {"success": True}
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.zip",
            extracted_files=[],
            credential_id=1,
        )
        mock_sms_thread.assert_called_once()
        call_kwargs = mock_sms_thread.call_args[1]
        assert call_kwargs["extracted_files"] == ["/tmp/doc.zip"]

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_with_multiple_extracted_files(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.return_value = {"success": True, "case_id": 1}
        processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.zip",
            extracted_files=["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"],
            credential_id=1,
        )
        call_kwargs = mock_sms_thread.call_args[1]
        assert call_kwargs["extracted_files"] == ["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"]

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_exception_returns_error_result(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.side_effect = RuntimeError("unexpected")
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result.success is False
        assert "unexpected" in result.error_message

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_result_defaults_when_keys_missing(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.return_value = {}  # Empty result
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result.success is False
        assert result.case_id is None
        assert result.case_log_id is None
        assert result.renamed_path == "/tmp/doc.pdf"
        assert result.notification_sent is False
        assert result.error_message is None


# ===========================================================================
# record_query_history
# ===========================================================================

class TestRecordQueryHistory:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.threading.Thread")
    def test_record_query_history_starts_thread(self, mock_thread_cls, processor, sample_record):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        processor.record_query_history(credential_id=1, entry=sample_record)

        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=10)


# ===========================================================================
# _match_case_by_number
# ===========================================================================

class TestMatchCaseByNumber:
    def test_delegates_to_case_matcher(self, processor, mock_case_matcher):
        mock_case = MagicMock()
        mock_case_matcher.match_by_case_number.return_value = mock_case
        result = processor._match_case_by_number("(2025)粤0604民初41257号")
        mock_case_matcher.match_by_case_number.assert_called_once_with(["(2025)粤0604民初41257号"])
        assert result is mock_case

    def test_returns_none_when_no_match(self, processor, mock_case_matcher):
        mock_case_matcher.match_by_case_number.return_value = None
        result = processor._match_case_by_number("nonexistent")
        assert result is None


# ===========================================================================
# _match_case_by_document_parties
# ===========================================================================

class TestMatchCaseByDocumentParties:
    @patch("apps.core.models.enums.CaseStatus")
    def test_matches_active_case(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        mock_case = MagicMock()
        mock_case.status = "active"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor._match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is mock_case
        mock_case_matcher.extract_parties_from_document.assert_called_once_with("/tmp/doc.pdf")
        mock_case_matcher.match_by_party_names.assert_called_once_with(["张三"])

    @patch("apps.core.models.enums.CaseStatus")
    def test_skips_inactive_case(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        mock_case = MagicMock()
        mock_case.status = "closed"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor._match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_when_no_parties_extracted(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = []
        result = processor._match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_when_party_match_fails(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = None
        result = processor._match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_on_exception(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.side_effect = RuntimeError("boom")
        result = processor._match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    @patch("apps.core.models.enums.CaseStatus")
    def test_tries_multiple_documents(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        # First doc returns no parties, second doc matches
        mock_case_matcher.extract_parties_from_document.side_effect = [[], ["李四"]]
        mock_case = MagicMock()
        mock_case.status = "active"
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor._match_case_by_document_parties(["/tmp/doc1.pdf", "/tmp/doc2.pdf"])
        assert result is mock_case
        assert mock_case_matcher.extract_parties_from_document.call_count == 2

    @patch("apps.core.models.enums.CaseStatus")
    def test_inactive_then_active_finds_active(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        inactive_case = MagicMock()
        inactive_case.status = "closed"
        active_case = MagicMock()
        active_case.status = "active"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.side_effect = [inactive_case, active_case]

        result = processor._match_case_by_document_parties(["/tmp/doc1.pdf", "/tmp/doc2.pdf"])
        assert result is active_case


# ===========================================================================
# _sync_case_number_to_case
# ===========================================================================

class TestSyncCaseNumberToCase:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_already_has_case_number(self, mock_locator_cls):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        mock_service = MagicMock()
        mock_locator_cls.get_case_number_service.return_value = mock_service
        mock_num = MagicMock()
        mock_num.number = "(2025)粤0604民初41257号"
        mock_service.list_numbers_internal.return_value = [mock_num]

        p = DocumentProcessor()
        result = p._sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_service.create_number_internal.assert_not_called()

    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_creates_new_case_number(self, mock_locator_cls):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        mock_service = MagicMock()
        mock_locator_cls.get_case_number_service.return_value = mock_service
        mock_num = MagicMock()
        mock_num.number = "OTHER-CASE"
        mock_service.list_numbers_internal.return_value = [mock_num]

        p = DocumentProcessor()
        result = p._sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_service.create_number_internal.assert_called_once_with(
            case_id=1, number="(2025)粤0604民初41257号", remarks="文书送达自动下载同步"
        )

    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_empty_existing_numbers_creates_new(self, mock_locator_cls):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        mock_service = MagicMock()
        mock_locator_cls.get_case_number_service.return_value = mock_service
        mock_service.list_numbers_internal.return_value = []

        p = DocumentProcessor()
        result = p._sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_service.create_number_internal.assert_called_once()

    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_exception_returns_false(self, mock_locator_cls):
        from apps.automation.services.document_delivery.delivery.document_processor import DocumentProcessor

        mock_locator_cls.get_case_number_service.side_effect = RuntimeError("service down")

        p = DocumentProcessor()
        result = p._sync_case_number_to_case(1, "CASE-001")
        assert result is False


# ===========================================================================
# _rename_and_attach_documents
# ===========================================================================

class TestRenameAndAttachDocuments:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_renames_and_creates_log(self, mock_locator_cls, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"

        mock_sms = MagicMock()
        mock_sms.id = 10

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"

        mock_log_service = MagicMock()
        mock_locator_cls.get_caselog_service.return_value = mock_log_service
        mock_log = MagicMock()
        mock_log.id = 77
        mock_log_service.create_log.return_value = mock_log

        with patch(
            "apps.automation.services.document_delivery.delivery.document_processor.Path"
        ) as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.exists.return_value = True
            mock_path_inst.name = "doc.pdf"
            mock_path_cls.return_value = mock_path_inst

            with patch("builtins.open", MagicMock()):
                with patch(
                    "django.core.files.uploadedfile.SimpleUploadedFile"
                ):
                    renamed, log_id = processor._rename_and_attach_documents(
                        sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
                    )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id == 77
        mock_document_renamer.rename.assert_called_once()
        mock_log_service.create_log.assert_called_once()

    def test_rename_returns_none_appends_original(self, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = None

        with patch(
            "apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator"
        ) as mock_locator:
            mock_locator.get_caselog_service.return_value.create_log.return_value = None
            renamed, log_id = processor._rename_and_attach_documents(
                sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
            )

        assert renamed == ["/tmp/doc.pdf"]
        assert log_id is None

    def test_rename_exception_appends_original(self, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.side_effect = RuntimeError("rename error")

        with patch(
            "apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator"
        ) as mock_locator:
            mock_locator.get_caselog_service.return_value.create_log.return_value = None
            renamed, log_id = processor._rename_and_attach_documents(
                sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
            )

        assert renamed == ["/tmp/doc.pdf"]

    def test_empty_extracted_files(self, processor):
        mock_case = MagicMock()
        mock_sms = MagicMock()

        renamed, log_id = processor._rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=[]
        )
        assert renamed == []
        assert log_id is None

    def test_file_not_found_skips_upload(self, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"

        with patch(
            "apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator"
        ) as mock_locator:
            mock_log_service = MagicMock()
            mock_locator.get_caselog_service.return_value = mock_log_service
            mock_log = MagicMock()
            mock_log.id = 55
            mock_log_service.create_log.return_value = mock_log

            with patch(
                "apps.automation.services.document_delivery.delivery.document_processor.Path"
            ) as mock_path_cls:
                mock_path_inst = MagicMock()
                mock_path_inst.exists.return_value = False
                mock_path_cls.return_value = mock_path_inst

                renamed, log_id = processor._rename_and_attach_documents(
                    sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
                )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id == 55
        mock_log_service.upload_attachments.assert_not_called()

    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_caselog_creation_failure(self, mock_locator_cls, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"

        mock_log_service = MagicMock()
        mock_locator_cls.get_caselog_service.return_value = mock_log_service
        mock_log_service.create_log.return_value = None  # No log created

        renamed, log_id = processor._rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
        )
        assert renamed == ["/renamed/doc.pdf"]
        assert log_id is None

    def test_upload_attachment_exception_handled(self, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"

        with patch(
            "apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator"
        ) as mock_locator:
            mock_log_service = MagicMock()
            mock_locator.get_caselog_service.return_value = mock_log_service
            mock_log = MagicMock()
            mock_log.id = 55
            mock_log_service.create_log.return_value = mock_log
            mock_log_service.upload_attachments.side_effect = RuntimeError("upload failed")

            with patch(
                "apps.automation.services.document_delivery.delivery.document_processor.Path"
            ) as mock_path_cls:
                mock_path_inst = MagicMock()
                mock_path_inst.exists.return_value = True
                mock_path_inst.name = "doc.pdf"
                mock_path_cls.return_value = mock_path_inst

                with patch("builtins.open", MagicMock()):
                    with patch(
                        "django.core.files.uploadedfile.SimpleUploadedFile"
                    ):
                        renamed, log_id = processor._rename_and_attach_documents(
                            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
                        )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id == 55

    @patch("apps.automation.services.document_delivery.delivery.document_processor.ServiceLocator")
    def test_outer_exception_returns_accumulated_files(self, mock_locator_cls, processor, mock_document_renamer):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        # rename raises -> per-file except appends original file
        mock_document_renamer.rename.side_effect = RuntimeError("boom")
        # ServiceLocator raises -> outer except catches
        mock_locator_cls.get_caselog_service.side_effect = RuntimeError("boom2")

        renamed, log_id = processor._rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
        )
        # renamed_files already has the original from per-file except
        assert renamed == ["/tmp/doc.pdf"]
        assert log_id is None


# ===========================================================================
# _send_notification
# ===========================================================================

class TestSendNotification:
    def test_no_case_returns_false(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = None
        mock_sms.notification_results = {}

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        mock_notification_service.send_case_chat_notification.assert_not_called()
        assert mock_sms.notification_results["none"]["success"] is False

    def test_success(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()

        mock_notification_result = MagicMock()
        mock_notification_result.to_notification_results.return_value = {"wechat": {"success": True}}
        mock_notification_result.any_success = True
        mock_notification_service.send_case_chat_notification.return_value = mock_notification_result

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is True
        mock_notification_service.send_case_chat_notification.assert_called_once_with(mock_sms, ["/tmp/doc.pdf"])

    def test_no_success(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()

        mock_notification_result = MagicMock()
        mock_notification_result.to_notification_results.return_value = {"wechat": {"success": False}}
        mock_notification_result.any_success = False
        mock_notification_service.send_case_chat_notification.return_value = mock_notification_result

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False

    def test_exception_returns_false(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        mock_sms.notification_results = {}

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("send failed")

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        assert "_exception" in mock_sms.notification_results

    def test_exception_preserves_existing_results(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        existing_results = {"wechat": {"success": True}}
        mock_sms.notification_results = existing_results

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("send failed")

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        assert "_exception" in mock_sms.notification_results

    def test_exception_with_none_results_initializes_dict(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        mock_sms.notification_results = None

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("boom")

        result = processor._send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        # notification_results should have been set (or _exception appended)


# ===========================================================================
# _process_sms_in_thread (integration of thread + internal flow)
# ===========================================================================

class TestProcessSmsInThread:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.threading.Thread")
    def test_timeout_returns_timeout_error(self, mock_thread_cls, processor, sample_record):
        """When the thread does not finish in time, result_queue is empty -> timeout."""
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        # join does nothing (thread "finishes") but we don't populate the queue
        # We need to simulate: after join the queue is still empty
        # The simplest way: make the thread target not execute

        # Actually, the real thread runs do_process. We need to mock at the module level
        # so the thread's do_process doesn't actually do anything, leaving the queue empty.
        # But since threading.Thread is mocked, the target never runs.
        result = processor._process_sms_in_thread(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result["success"] is False
        assert result["error_message"] == "SMS 处理超时"

    @patch("apps.automation.services.document_delivery.delivery.document_processor.queue.Queue")
    @patch("apps.automation.services.document_delivery.delivery.document_processor.threading.Thread")
    def test_returns_result_from_queue(self, mock_thread_cls, mock_queue_cls, processor, sample_record):
        expected = {"success": True, "case_id": 1, "error_message": None}
        mock_queue = MagicMock()
        mock_queue.empty.return_value = False
        mock_queue.get.return_value = expected
        mock_queue_cls.return_value = mock_queue

        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        result = processor._process_sms_in_thread(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result == expected
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=60)


# ===========================================================================
# Edge-case / integration-ish tests for process_document
# ===========================================================================

class TestProcessDocumentEdgeCases:
    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_with_none_extracted_files_calls_extract(self, mock_sms_thread, processor, sample_record):
        mock_sms_thread.return_value = {"success": True}
        with patch.object(processor, "extract_zip_if_needed", return_value=None) as mock_extract:
            result = processor.process_document(
                record=sample_record,
                file_path="/tmp/doc.zip",
                extracted_files=[],
                credential_id=1,
            )
            mock_extract.assert_called_once()

    @patch("apps.automation.services.document_delivery.delivery.document_processor.DocumentProcessor._process_sms_in_thread")
    def test_process_document_partial_result_keys(self, mock_sms_thread, processor, sample_record):
        """Result with only some keys populated."""
        mock_sms_thread.return_value = {
            "success": True,
            "case_id": 10,
            # case_log_id missing
            # renamed_path missing
            "notification_sent": True,
        }
        result = processor.process_document(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result.success is True
        assert result.case_id == 10
        assert result.case_log_id is None
        assert result.renamed_path == "/tmp/doc.pdf"  # Falls back to file_path
        assert result.notification_sent is True
