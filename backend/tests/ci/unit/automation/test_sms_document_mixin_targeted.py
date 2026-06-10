"""Targeted tests for SMSDocumentMixin and DocumentAttachmentService."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskType


# ── SMSDocumentMixin tests ────────────────────────────────────────


@pytest.fixture
def sms_document_mixin():
    """Create a concrete instance of SMSDocumentMixin for testing."""
    from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin

    class ConcreteMixin(SMSDocumentMixin):
        _case_number_extractor_mock = None
        _matcher_mock = None
        _document_attachment_mock = None
        _case_folder_archive_mock = None

        @property
        def case_number_extractor(self):
            if self._case_number_extractor_mock is None:
                self._case_number_extractor_mock = MagicMock()
            return self._case_number_extractor_mock

        @property
        def document_attachment(self):
            if self._document_attachment_mock is None:
                self._document_attachment_mock = MagicMock()
            return self._document_attachment_mock

        @property
        def matcher(self):
            if self._matcher_mock is None:
                self._matcher_mock = MagicMock()
            return self._matcher_mock

        @property
        def case_folder_archive(self):
            if self._case_folder_archive_mock is None:
                self._case_folder_archive_mock = MagicMock()
            return self._case_folder_archive_mock

    return ConcreteMixin()


@pytest.fixture
def court_sms(db):
    return CourtSMS.objects.create(
        content="测试短信",
        received_at=timezone.now(),
        status=CourtSMSStatus.MATCHING,
    )


@pytest.mark.django_db
class TestExtractAndUpdateFromDocuments:
    def test_no_scraper_task_skips(self, sms_document_mixin, court_sms):
        court_sms.scraper_task = None
        court_sms.save()
        sms_document_mixin._extract_and_update_sms_from_documents(court_sms)
        # No error means it returned early

    def test_no_document_paths_skips(self, sms_document_mixin, court_sms):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com"
        )
        court_sms.scraper_task = task
        court_sms.save()
        sms_document_mixin._extract_and_update_sms_from_documents(court_sms)

    def test_extracts_from_documents(self, sms_document_mixin, court_sms, tmp_path):
        doc = tmp_path / "test.pdf"
        doc.write_bytes(b"test")

        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [str(doc)]},
        )
        court_sms.scraper_task = task
        court_sms.save()

        sms_document_mixin.case_number_extractor.extract_from_document.return_value = ["（2024）京0101民初1234号"]
        sms_document_mixin.matcher.extract_parties_from_document.return_value = ["张某"]

        sms_document_mixin._extract_and_update_sms_from_documents(court_sms)
        court_sms.refresh_from_db()
        assert "（2024）京0101民初1234号" in court_sms.case_numbers
        assert "张某" in court_sms.party_names


@pytest.mark.django_db
class TestExtractFromSingleDocument:
    def test_extracts_case_numbers(self, sms_document_mixin):
        case_numbers = []
        party_names = []
        sms_document_mixin.case_number_extractor.extract_from_document.return_value = ["（2024）京0101民初1234号"]

        result = sms_document_mixin._extract_from_single_document("/path/to/doc.pdf", case_numbers, party_names)
        assert result is True
        assert case_numbers == ["（2024）京0101民初1234号"]

    def test_extracts_party_names(self, sms_document_mixin):
        case_numbers = ["已存在案号"]
        party_names = []
        sms_document_mixin.matcher.extract_parties_from_document.return_value = ["张某", "李某"]

        result = sms_document_mixin._extract_from_single_document("/path/to/doc.pdf", case_numbers, party_names)
        assert result is True
        assert party_names == ["张某", "李某"]

    def test_no_extraction(self, sms_document_mixin):
        case_numbers = ["已存在"]
        party_names = ["已存在"]
        result = sms_document_mixin._extract_from_single_document("/path/to/doc.pdf", case_numbers, party_names)
        assert result is False

    def test_handles_exception(self, sms_document_mixin):
        case_numbers = []
        party_names = []
        sms_document_mixin.case_number_extractor.extract_from_document.side_effect = Exception("boom")

        result = sms_document_mixin._extract_from_single_document("/path/to/doc.pdf", case_numbers, party_names)
        assert result is False


@pytest.mark.django_db
class TestGetDocumentPathsForExtraction:
    def test_paths_from_document_file_paths(self, sms_document_mixin, court_sms, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        court_sms.document_file_paths = [str(doc)]
        court_sms.save()

        paths = sms_document_mixin._get_document_paths_for_extraction(court_sms)
        assert str(doc) in paths

    def test_paths_from_scraper_task_result(self, sms_document_mixin, court_sms, tmp_path):
        doc = tmp_path / "doc2.pdf"
        doc.write_bytes(b"test")
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [str(doc)]},
        )
        court_sms.scraper_task = task
        court_sms.save()

        paths = sms_document_mixin._get_document_paths_for_extraction(court_sms)
        assert str(doc) in paths

    def test_deduplicates_paths(self, sms_document_mixin, court_sms, tmp_path):
        doc = tmp_path / "doc3.pdf"
        doc.write_bytes(b"test")
        court_sms.document_file_paths = [str(doc), str(doc)]
        court_sms.save()

        paths = sms_document_mixin._get_document_paths_for_extraction(court_sms)
        assert len(paths) == 1


@pytest.mark.django_db
class TestProcessRenaming:
    def test_no_scraper_task(self, sms_document_mixin, court_sms):
        court_sms.scraper_task = None
        court_sms.save()
        result = sms_document_mixin._process_renaming(court_sms)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.NOTIFYING

    def test_no_document_paths(self, sms_document_mixin, court_sms):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com"
        )
        court_sms.scraper_task = task
        court_sms.save()
        sms_document_mixin.document_attachment.get_paths_for_renaming.return_value = []

        result = sms_document_mixin._process_renaming(court_sms)
        result.refresh_from_db()
        assert result.status == CourtSMSStatus.NOTIFYING


@pytest.mark.django_db
class TestSaveRenamedPaths:
    def test_saves_to_scraper_task(self, sms_document_mixin, court_sms):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": ["old.pdf"]},
        )
        court_sms.scraper_task = task
        court_sms.save()

        sms_document_mixin._save_renamed_paths(court_sms, ["/new/path.pdf"])
        task.refresh_from_db()
        assert task.result["renamed_files"] == ["/new/path.pdf"]

    def test_empty_paths_skips(self, sms_document_mixin, court_sms):
        sms_document_mixin._save_renamed_paths(court_sms, [])
        # No error

    def test_no_scraper_task_skips(self, sms_document_mixin, court_sms):
        court_sms.scraper_task = None
        court_sms.save()
        sms_document_mixin._save_renamed_paths(court_sms, ["/path.pdf"])
        # No error


@pytest.mark.django_db
class TestAttachToCaseLog:
    def test_no_renamed_paths(self, sms_document_mixin, court_sms):
        sms_document_mixin._attach_to_case_log(court_sms, [])
        # No error

    def test_with_case_log_calls_attachment(self, sms_document_mixin):
        """Test using MagicMock SMS (not saved to DB) to avoid FK assignment issues."""
        sms = MagicMock()
        sms.case_log = MagicMock()
        sms.case_log.id = 100
        sms_document_mixin._attach_to_case_log(sms, ["/path.pdf"])
        sms_document_mixin.document_attachment.add_to_case_log.assert_called_once()


@pytest.mark.django_db
class TestSyncCaseNumbersFromDocuments:
    def test_no_case(self, sms_document_mixin, court_sms):
        court_sms.case = None
        sms_document_mixin._sync_case_numbers_from_documents(court_sms, ["/path.pdf"])

    def test_no_renamed_paths(self, sms_document_mixin, court_sms):
        sms_document_mixin._sync_case_numbers_from_documents(court_sms, [])

    def test_already_has_case_numbers_skips_extraction(self, sms_document_mixin, tmp_path):
        """Test with MagicMock SMS to avoid FK assignment issues."""
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        sms = MagicMock()
        sms.case_numbers = ["（2024）京0101民初1234号"]
        sms.case = MagicMock()
        sms.case.id = 42
        sms_document_mixin._sync_case_numbers_from_documents(sms, [str(doc)])
        sms_document_mixin.case_number_extractor.extract_from_document.assert_not_called()


@pytest.mark.django_db
class TestSyncPartyNamesFromDocuments:
    def test_no_renamed_paths(self, sms_document_mixin, court_sms):
        sms_document_mixin._sync_party_names_from_documents(court_sms, [])

    def test_already_has_parties(self, sms_document_mixin, court_sms):
        court_sms.party_names = ["张某"]
        sms_document_mixin._sync_party_names_from_documents(court_sms, ["/path.pdf"])
        sms_document_mixin.matcher.extract_parties_from_document.assert_not_called()


@pytest.mark.django_db
class TestArchiveToCaseFolder:
    def test_no_case_id(self, sms_document_mixin, court_sms):
        court_sms.case_id = None
        sms_document_mixin._archive_to_case_folder(court_sms, ["/path.pdf"])

    def test_no_paths(self, sms_document_mixin, court_sms):
        sms_document_mixin._archive_to_case_folder(court_sms, [])

    def test_calls_archive(self, sms_document_mixin):
        """Test with MagicMock SMS to avoid FK assignment issues."""
        sms = MagicMock()
        sms.case_id = 42
        sms_document_mixin.case_folder_archive.archive_sms_documents.return_value = True
        sms_document_mixin._archive_to_case_folder(sms, ["/path.pdf"])
        sms_document_mixin.case_folder_archive.archive_sms_documents.assert_called_once()
