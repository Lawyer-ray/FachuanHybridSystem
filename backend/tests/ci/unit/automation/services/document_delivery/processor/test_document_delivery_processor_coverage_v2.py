"""
Comprehensive unit tests for DocumentDeliveryProcessor (processor/).

Covers every public and private method including error paths and edge cases.
All external dependencies (DB, HTTP, file I/O, threading, Django ORM) are mocked.
"""

import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
)

# Module path under test
MOD = "apps.automation.services.document_delivery.processor.document_delivery_processor"


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
def mock_caselog_service():
    return MagicMock()


@pytest.fixture
def mock_case_number_service():
    return MagicMock()


@pytest.fixture
def processor(
    mock_case_matcher,
    mock_document_renamer,
    mock_notification_service,
    mock_caselog_service,
    mock_case_number_service,
):
    from apps.automation.services.document_delivery.processor.document_delivery_processor import (
        DocumentDeliveryProcessor,
    )

    return DocumentDeliveryProcessor(
        case_matcher=mock_case_matcher,
        document_renamer=mock_document_renamer,
        notification_service=mock_notification_service,
        caselog_service=mock_caselog_service,
        case_number_service=mock_case_number_service,
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


def _make_zip(tmp_path, file_names=None):
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
    def test_init_with_all_deps(
        self,
        mock_case_matcher,
        mock_document_renamer,
        mock_notification_service,
        mock_caselog_service,
        mock_case_number_service,
    ):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor(
            case_matcher=mock_case_matcher,
            document_renamer=mock_document_renamer,
            notification_service=mock_notification_service,
            caselog_service=mock_caselog_service,
            case_number_service=mock_case_number_service,
        )
        assert p._case_matcher is mock_case_matcher
        assert p._document_renamer is mock_document_renamer
        assert p._notification_service is mock_notification_service
        assert p._caselog_service is mock_caselog_service
        assert p._case_number_service is mock_case_number_service

    def test_init_with_no_deps(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        assert p._case_matcher is None
        assert p._document_renamer is None
        assert p._notification_service is None
        assert p._caselog_service is None
        assert p._case_number_service is None


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

    def test_caselog_service_returns_injected(self, processor, mock_caselog_service):
        assert processor.caselog_service is mock_caselog_service

    def test_case_number_service_returns_injected(self, processor, mock_case_number_service):
        assert processor.case_number_service is mock_case_number_service

    def test_case_matcher_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        mock_cm = MagicMock()
        with patch(f"apps.automation.services.sms.case_matcher.CaseMatcher", return_value=mock_cm):
            result = p.case_matcher
        assert result is mock_cm
        # Second call should return cached value
        assert p.case_matcher is mock_cm

    def test_document_renamer_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        mock_dr = MagicMock()
        with patch(f"apps.automation.services.sms.document_renamer.DocumentRenamer", return_value=mock_dr):
            result = p.document_renamer
        assert result is mock_dr

    def test_notification_service_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        mock_ns = MagicMock()
        with patch(
            f"apps.automation.services.sms.sms_notification_service.SMSNotificationService",
            return_value=mock_ns,
        ):
            result = p.notification_service
        assert result is mock_ns

    def test_caselog_service_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        mock_cl = MagicMock()
        with patch(
            f"apps.core.dependencies.business_case.build_case_log_service",
            return_value=mock_cl,
        ):
            result = p.caselog_service
        assert result is mock_cl

    def test_case_number_service_lazy_loads_when_none(self):
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        p = DocumentDeliveryProcessor()
        mock_cn = MagicMock()
        with patch(
            f"apps.core.dependencies.business_case.build_case_number_service",
            return_value=mock_cn,
        ):
            result = p.case_number_service
        assert result is mock_cn


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
        assert result is not None
        assert len(result) == 1
        assert any("safe.txt" in f for f in result)

    def test_zip_extraction_error_returns_none(self, processor):
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

    def test_zip_with_subdirectories(self, processor, tmp_path):
        zip_path = tmp_path / "nested.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("subdir/nested.pdf", "data")
            zf.writestr("top.pdf", "data")
        result = processor.extract_zip_if_needed(str(zip_path))
        assert result is not None
        assert len(result) == 2

    def test_non_zip_dotzip_in_middle_returns_none(self, processor):
        """File with .zip in the middle but different extension."""
        assert processor.extract_zip_if_needed("/some/file.zip.bak") is None


# ===========================================================================
# process_downloaded_document
# ===========================================================================


class TestProcessDownloadedDocument:
    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_success_with_extracted_files(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = ["/tmp/doc1.pdf", "/tmp/doc2.pdf"]
        mock_sms.return_value = {
            "success": True,
            "case_id": 42,
            "case_log_id": 99,
            "renamed_path": "/renamed/doc.pdf",
            "notification_sent": True,
            "error_message": None,
        }
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.zip",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is True
        assert result.case_id == 42
        assert result.case_log_id == 99
        assert result.renamed_path == "/renamed/doc.pdf"
        assert result.notification_sent is True
        assert result.error_message is None
        mock_extract.assert_called_once_with("/tmp/doc.zip")

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_extract_returns_none_uses_file_path(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = None
        mock_sms.return_value = {"success": True, "case_id": 1}
        processor.process_downloaded_document(
            file_path="/tmp/doc.pdf",
            record=sample_record,
            credential_id=1,
        )
        call_kwargs = mock_sms.call_args[1]
        assert call_kwargs["extracted_files"] == ["/tmp/doc.pdf"]

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_extract_returns_empty_list_uses_file_path(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = []
        mock_sms.return_value = {"success": True}
        processor.process_downloaded_document(
            file_path="/tmp/doc.zip",
            record=sample_record,
            credential_id=1,
        )
        call_kwargs = mock_sms.call_args[1]
        assert call_kwargs["extracted_files"] == ["/tmp/doc.zip"]

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_failure_result(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = None
        mock_sms.return_value = {
            "success": False,
            "error_message": "some error",
        }
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.pdf",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is False
        assert result.error_message == "some error"

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_exception_in_extract_returns_error_result(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.side_effect = RuntimeError("extract exploded")
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.zip",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is False
        assert "extract exploded" in result.error_message

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_exception_in_sms_thread_returns_error_result(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = ["/tmp/doc.pdf"]
        mock_sms.side_effect = RuntimeError("thread exploded")
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.zip",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is False
        assert "thread exploded" in result.error_message

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_partial_result_keys_defaults(self, mock_extract, mock_sms, processor, sample_record):
        """Result with only some keys populated defaults correctly."""
        mock_extract.return_value = None
        mock_sms.return_value = {"success": True, "case_id": 10}
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.pdf",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is True
        assert result.case_id == 10
        assert result.case_log_id is None
        assert result.renamed_path == "/tmp/doc.pdf"
        assert result.notification_sent is False
        assert result.error_message is None

    @patch(f"{MOD}.DocumentDeliveryProcessor.process_sms_in_thread")
    @patch(f"{MOD}.DocumentDeliveryProcessor.extract_zip_if_needed")
    def test_empty_result_dict(self, mock_extract, mock_sms, processor, sample_record):
        mock_extract.return_value = None
        mock_sms.return_value = {}
        result = processor.process_downloaded_document(
            file_path="/tmp/doc.pdf",
            record=sample_record,
            credential_id=1,
        )
        assert result.success is False
        assert result.case_id is None
        assert result.renamed_path == "/tmp/doc.pdf"


# ===========================================================================
# process_sms_in_thread
# ===========================================================================


class TestProcessSmsInThread:
    @patch(f"{MOD}.threading.Thread")
    def test_timeout_returns_timeout_error(self, mock_thread_cls, processor, sample_record):
        """When the thread does not finish in time, result_queue is empty."""
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        # Thread target never runs because Thread is mocked
        result = processor.process_sms_in_thread(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result["success"] is False
        assert result["error_message"] == "SMS 处理超时"

    @patch(f"{MOD}.queue.Queue")
    @patch(f"{MOD}.threading.Thread")
    def test_returns_result_from_queue(self, mock_thread_cls, mock_queue_cls, processor, sample_record):
        expected = {"success": True, "case_id": 1, "error_message": None}
        mock_queue = MagicMock()
        mock_queue.empty.return_value = False
        mock_queue.get.return_value = expected
        mock_queue_cls.return_value = mock_queue

        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        result = processor.process_sms_in_thread(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        assert result == expected
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=60)

    @patch(f"{MOD}.queue.Queue")
    @patch(f"{MOD}.threading.Thread")
    def test_thread_started_and_joined(self, mock_thread_cls, mock_queue_cls, processor, sample_record):
        mock_queue = MagicMock()
        mock_queue.empty.return_value = False
        mock_queue.get.return_value = {"success": True}
        mock_queue_cls.return_value = mock_queue
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        processor.process_sms_in_thread(
            record=sample_record,
            file_path="/tmp/doc.pdf",
            extracted_files=["/tmp/doc.pdf"],
            credential_id=1,
        )
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=60)


# ===========================================================================
# record_query_history_in_thread
# ===========================================================================


class TestRecordQueryHistoryInThread:
    @patch(f"{MOD}.threading.Thread")
    def test_starts_thread_and_joins(self, mock_thread_cls, processor, sample_record):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        processor.record_query_history_in_thread(credential_id=1, entry=sample_record)

        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=10)


# ===========================================================================
# match_case_by_number
# ===========================================================================


class TestMatchCaseByNumber:
    def test_delegates_to_case_matcher(self, processor, mock_case_matcher):
        mock_case = MagicMock()
        mock_case_matcher.match_by_case_number.return_value = mock_case
        result = processor.match_case_by_number("(2025)粤0604民初41257号")
        mock_case_matcher.match_by_case_number.assert_called_once_with(["(2025)粤0604民初41257号"])
        assert result is mock_case

    def test_returns_none_when_no_match(self, processor, mock_case_matcher):
        mock_case_matcher.match_by_case_number.return_value = None
        result = processor.match_case_by_number("nonexistent")
        assert result is None


# ===========================================================================
# match_case_by_document_parties
# ===========================================================================


class TestMatchCaseByDocumentParties:
    @patch(f"apps.core.models.enums.CaseStatus")
    def test_matches_active_case(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        mock_case = MagicMock()
        mock_case.status = "active"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is mock_case
        mock_case_matcher.extract_parties_from_document.assert_called_once_with("/tmp/doc.pdf")
        mock_case_matcher.match_by_party_names.assert_called_once_with(["张三"])

    @patch(f"apps.core.models.enums.CaseStatus")
    def test_skips_inactive_case(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        mock_case = MagicMock()
        mock_case.status = "closed"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_when_no_parties_extracted(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = []
        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_when_party_match_fails(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.return_value = None
        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_returns_none_on_exception(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.side_effect = RuntimeError("boom")
        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    @patch(f"apps.core.models.enums.CaseStatus")
    def test_tries_multiple_documents(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        mock_case_matcher.extract_parties_from_document.side_effect = [[], ["李四"]]
        mock_case = MagicMock()
        mock_case.status = "active"
        mock_case_matcher.match_by_party_names.return_value = mock_case

        result = processor.match_case_by_document_parties(["/tmp/doc1.pdf", "/tmp/doc2.pdf"])
        assert result is mock_case
        assert mock_case_matcher.extract_parties_from_document.call_count == 2

    @patch(f"apps.core.models.enums.CaseStatus")
    def test_inactive_then_active_finds_active(self, mock_status_enum, processor, mock_case_matcher):
        mock_status_enum.ACTIVE = "active"
        inactive_case = MagicMock()
        inactive_case.status = "closed"
        active_case = MagicMock()
        active_case.status = "active"
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.side_effect = [inactive_case, active_case]

        result = processor.match_case_by_document_parties(["/tmp/doc1.pdf", "/tmp/doc2.pdf"])
        assert result is active_case

    def test_returns_none_when_extract_returns_none(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = None
        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None

    def test_exception_in_match_by_party_names(self, processor, mock_case_matcher):
        mock_case_matcher.extract_parties_from_document.return_value = ["张三"]
        mock_case_matcher.match_by_party_names.side_effect = RuntimeError("match failed")
        result = processor.match_case_by_document_parties(["/tmp/doc.pdf"])
        assert result is None


# ===========================================================================
# rename_and_attach_documents
# ===========================================================================


class TestRenameAndAttachDocuments:
    def test_renames_and_creates_log(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()
        mock_sms.id = 10

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"
        mock_system_user = MagicMock()
        mock_log = MagicMock()
        mock_log.id = 77
        mock_caselog_service.create_log.return_value = mock_log

        with patch.object(processor, "_get_system_user", return_value=mock_system_user):
            with patch.object(Path, "exists", return_value=True):
                with patch("builtins.open", MagicMock()):
                    with patch("django.core.files.uploadedfile.SimpleUploadedFile"):
                        renamed, log_id = processor.rename_and_attach_documents(
                            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
                        )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id == 77
        mock_document_renamer.rename.assert_called_once()
        mock_caselog_service.create_log.assert_called_once()

    def test_rename_returns_none_appends_original(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = None
        mock_caselog_service.create_log.return_value = None

        renamed, log_id = processor.rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
        )

        assert renamed == ["/tmp/doc.pdf"]
        assert log_id is None

    def test_rename_exception_appends_original(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.side_effect = RuntimeError("rename error")
        mock_caselog_service.create_log.return_value = None

        renamed, log_id = processor.rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
        )

        assert renamed == ["/tmp/doc.pdf"]

    def test_empty_extracted_files(self, processor):
        mock_case = MagicMock()
        mock_sms = MagicMock()

        renamed, log_id = processor.rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=[]
        )
        assert renamed == []
        assert log_id is None

    def test_file_not_found_skips_upload(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"
        mock_system_user = MagicMock()
        mock_log = MagicMock()
        mock_log.id = 55
        mock_caselog_service.create_log.return_value = mock_log

        with patch.object(processor, "_get_system_user", return_value=mock_system_user):
            with patch.object(Path, "exists", return_value=False):
                renamed, log_id = processor.rename_and_attach_documents(
                    sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
                )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id == 55
        mock_caselog_service.upload_attachments.assert_not_called()

    def test_caselog_creation_returns_none(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"
        mock_caselog_service.create_log.return_value = None

        renamed, log_id = processor.rename_and_attach_documents(
            sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
        )
        assert renamed == ["/renamed/doc.pdf"]
        assert log_id is None

    def test_no_system_user_returns_early(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        mock_document_renamer.rename.return_value = "/renamed/doc.pdf"

        with patch.object(processor, "_get_system_user", return_value=None):
            renamed, log_id = processor.rename_and_attach_documents(
                sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
            )

        assert renamed == ["/renamed/doc.pdf"]
        assert log_id is None
        mock_caselog_service.create_log.assert_not_called()

    def test_outer_exception_returns_accumulated_files(
        self, processor, mock_document_renamer, mock_caselog_service
    ):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        # rename raises -> per-file except appends original file
        mock_document_renamer.rename.side_effect = RuntimeError("boom")

        with patch.object(processor, "_get_system_user", side_effect=RuntimeError("service down")):
            renamed, log_id = processor.rename_and_attach_documents(
                sms=mock_sms, case=mock_case, extracted_files=["/tmp/doc.pdf"]
            )
        assert renamed == ["/tmp/doc.pdf"]
        assert log_id is None

    def test_multiple_files_rename_mix(self, processor, mock_document_renamer, mock_caselog_service):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_sms = MagicMock()

        # First file renames OK, second raises, third returns None
        mock_document_renamer.rename.side_effect = ["/renamed/a.pdf", RuntimeError("fail"), None]
        mock_system_user = MagicMock()
        mock_log = MagicMock()
        mock_log.id = 10
        mock_caselog_service.create_log.return_value = mock_log

        with patch.object(processor, "_get_system_user", return_value=mock_system_user):
            with patch.object(Path, "exists", return_value=True):
                with patch("builtins.open", MagicMock()):
                    with patch("django.core.files.uploadedfile.SimpleUploadedFile"):
                        renamed, log_id = processor.rename_and_attach_documents(
                            sms=mock_sms, case=mock_case,
                            extracted_files=["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"],
                        )

        assert renamed == ["/renamed/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"]
        assert log_id == 10


# ===========================================================================
# _upload_attachments
# ===========================================================================


class TestUploadAttachments:
    def test_uploads_existing_files(self, processor, mock_caselog_service):
        mock_log = MagicMock()

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("django.core.files.uploadedfile.SimpleUploadedFile") as mock_suf:
                    mock_uploaded = MagicMock()
                    mock_suf.return_value = mock_uploaded
                    processor._upload_attachments(mock_caselog_service, log_id=1, file_paths=["/tmp/doc.pdf"])

        mock_caselog_service.upload_attachments.assert_called_once()

    def test_skips_nonexistent_files(self, processor, mock_caselog_service):
        with patch.object(Path, "exists", return_value=False):
            processor._upload_attachments(mock_caselog_service, log_id=1, file_paths=["/tmp/missing.pdf"])

        mock_caselog_service.upload_attachments.assert_not_called()

    def test_upload_exception_handled(self, processor, mock_caselog_service):
        mock_caselog_service.upload_attachments.side_effect = RuntimeError("upload fail")

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("django.core.files.uploadedfile.SimpleUploadedFile"):
                    # Should not raise
                    processor._upload_attachments(mock_caselog_service, log_id=1, file_paths=["/tmp/doc.pdf"])

    def test_file_read_exception_handled(self, processor, mock_caselog_service):
        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", side_effect=IOError("read fail")):
                # Should not raise
                processor._upload_attachments(mock_caselog_service, log_id=1, file_paths=["/tmp/doc.pdf"])

    def test_empty_file_paths(self, processor, mock_caselog_service):
        processor._upload_attachments(mock_caselog_service, log_id=1, file_paths=[])
        mock_caselog_service.upload_attachments.assert_not_called()

    def test_multiple_files(self, processor, mock_caselog_service):
        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("django.core.files.uploadedfile.SimpleUploadedFile"):
                    processor._upload_attachments(
                        mock_caselog_service, log_id=1, file_paths=["/tmp/a.pdf", "/tmp/b.pdf"]
                    )

        assert mock_caselog_service.upload_attachments.call_count == 2


# ===========================================================================
# _get_system_user
# ===========================================================================


class TestGetSystemUser:
    def test_returns_lawyer_model(self, processor):
        mock_lawyer_service = MagicMock()
        mock_admin = MagicMock()
        mock_admin.id = 42
        mock_lawyer_service.get_admin_lawyer.return_value = mock_admin
        mock_lawyer_model = MagicMock()
        mock_lawyer_service.get_lawyer_model.return_value = mock_lawyer_model

        with patch(f"apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_locator.get_lawyer_service.return_value = mock_lawyer_service
            result = processor._get_system_user()

        assert result is mock_lawyer_model
        mock_lawyer_service.get_lawyer_model.assert_called_once_with(42)

    def test_returns_none_when_no_admin(self, processor):
        mock_lawyer_service = MagicMock()
        mock_lawyer_service.get_admin_lawyer.return_value = None

        with patch(f"apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_locator.get_lawyer_service.return_value = mock_lawyer_service
            result = processor._get_system_user()

        assert result is None

    def test_returns_none_on_exception(self, processor):
        with patch(f"apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_locator.get_lawyer_service.side_effect = RuntimeError("service down")
            result = processor._get_system_user()

        assert result is None


# ===========================================================================
# archive_to_case_folder
# ===========================================================================


class TestArchiveToCaseFolder:
    def test_no_case_id_returns_early(self, processor):
        mock_sms = MagicMock()
        mock_sms.case_id = None
        processor.archive_to_case_folder(mock_sms, ["/tmp/doc.pdf"])
        # Should not raise

    def test_empty_renamed_paths_returns_early(self, processor):
        mock_sms = MagicMock()
        mock_sms.case_id = 1
        processor.archive_to_case_folder(mock_sms, [])
        # Should not raise

    def test_archives_successfully(self, processor):
        mock_sms = MagicMock()
        mock_sms.case_id = 1
        mock_sms.id = 10

        with patch(
            f"apps.automation.services.sms.case_folder_archive_service.CaseFolderArchiveService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.archive_sms_documents.return_value = True
            mock_service_cls.return_value = mock_service

            processor.archive_to_case_folder(mock_sms, ["/tmp/doc.pdf"])

        mock_service.archive_sms_documents.assert_called_once_with(mock_sms, ["/tmp/doc.pdf"])

    def test_archive_returns_false_still_ok(self, processor):
        mock_sms = MagicMock()
        mock_sms.case_id = 1
        mock_sms.id = 10

        with patch(
            f"apps.automation.services.sms.case_folder_archive_service.CaseFolderArchiveService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.archive_sms_documents.return_value = False
            mock_service_cls.return_value = mock_service

            # Should not raise
            processor.archive_to_case_folder(mock_sms, ["/tmp/doc.pdf"])

    def test_archive_exception_handled(self, processor):
        mock_sms = MagicMock()
        mock_sms.case_id = 1
        mock_sms.id = 10

        with patch(
            f"apps.automation.services.sms.case_folder_archive_service.CaseFolderArchiveService"
        ) as mock_service_cls:
            mock_service_cls.side_effect = RuntimeError("archive fail")

            # Should not raise
            processor.archive_to_case_folder(mock_sms, ["/tmp/doc.pdf"])


# ===========================================================================
# send_notification
# ===========================================================================


class TestSendNotification:
    def test_no_case_returns_false(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = None
        mock_sms.notification_results = {}

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
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

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is True
        mock_notification_service.send_case_chat_notification.assert_called_once_with(
            mock_sms, ["/tmp/doc.pdf"]
        )

    def test_no_success(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()

        mock_notification_result = MagicMock()
        mock_notification_result.to_notification_results.return_value = {"wechat": {"success": False}}
        mock_notification_result.any_success = False
        mock_notification_service.send_case_chat_notification.return_value = mock_notification_result

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False

    def test_exception_returns_false(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        mock_sms.notification_results = {}

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("send failed")

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        assert "_exception" in mock_sms.notification_results

    def test_exception_preserves_existing_results(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        existing_results = {"wechat": {"success": True}}
        mock_sms.notification_results = existing_results

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("send failed")

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False
        assert "_exception" in mock_sms.notification_results

    def test_exception_with_none_results_initializes(self, processor, mock_notification_service):
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.case = MagicMock()
        mock_sms.notification_results = None

        mock_notification_service.send_case_chat_notification.side_effect = RuntimeError("boom")

        result = processor.send_notification(mock_sms, ["/tmp/doc.pdf"])
        assert result is False


# ===========================================================================
# sync_case_number_to_case
# ===========================================================================


class TestSyncCaseNumberToCase:
    def test_already_has_case_number(self, processor, mock_case_number_service):
        mock_num = MagicMock()
        mock_num.number = "(2025)粤0604民初41257号"
        mock_case_number_service.list_numbers_internal.return_value = [mock_num]

        result = processor.sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_case_number_service.create_number_internal.assert_not_called()

    def test_creates_new_case_number(self, processor, mock_case_number_service):
        mock_num = MagicMock()
        mock_num.number = "OTHER-CASE"
        mock_case_number_service.list_numbers_internal.return_value = [mock_num]

        result = processor.sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_case_number_service.create_number_internal.assert_called_once_with(
            case_id=1, number="(2025)粤0604民初41257号", remarks="文书送达自动下载同步"
        )

    def test_empty_existing_numbers_creates_new(self, processor, mock_case_number_service):
        mock_case_number_service.list_numbers_internal.return_value = []

        result = processor.sync_case_number_to_case(1, "(2025)粤0604民初41257号")
        assert result is True
        mock_case_number_service.create_number_internal.assert_called_once()

    def test_fallback_to_list_numbers_when_internal_not_available(self, processor, mock_case_number_service):
        """If list_numbers_internal doesn't exist, fall back to list_numbers."""
        del mock_case_number_service.list_numbers_internal
        del mock_case_number_service.create_number_internal
        mock_case_number_service.list_numbers.return_value = []
        mock_case_number_service.create_number.return_value = MagicMock()

        result = processor.sync_case_number_to_case(1, "CASE-001")
        assert result is True
        mock_case_number_service.list_numbers.assert_called_once_with(case_id=1)
        mock_case_number_service.create_number.assert_called_once()

    def test_no_list_or_create_methods_returns_false(self, processor, mock_case_number_service):
        """If neither internal nor public methods exist, returns False."""
        # Remove all methods
        for attr in ["list_numbers_internal", "list_numbers", "create_number_internal", "create_number"]:
            if hasattr(mock_case_number_service, attr):
                delattr(mock_case_number_service, attr)

        result = processor.sync_case_number_to_case(1, "CASE-001")
        assert result is False

    def test_no_create_method_returns_false(self, processor, mock_case_number_service):
        """If create method doesn't exist, returns False."""
        mock_case_number_service.list_numbers_internal.return_value = []
        for attr in ["create_number_internal", "create_number"]:
            if hasattr(mock_case_number_service, attr):
                delattr(mock_case_number_service, attr)

        result = processor.sync_case_number_to_case(1, "CASE-001")
        assert result is False

    def test_exception_returns_false(self, processor, mock_case_number_service):
        mock_case_number_service.list_numbers_internal.side_effect = RuntimeError("service down")

        result = processor.sync_case_number_to_case(1, "CASE-001")
        assert result is False

    def test_number_with_none_attr_handled(self, processor, mock_case_number_service):
        """Existing number object whose .number is None should not match."""
        mock_num = MagicMock()
        mock_num.number = None
        mock_case_number_service.list_numbers_internal.return_value = [mock_num]

        result = processor.sync_case_number_to_case(1, "CASE-001")
        assert result is True
        mock_case_number_service.create_number_internal.assert_called_once()
