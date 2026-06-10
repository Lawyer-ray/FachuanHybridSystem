"""Targeted tests for DocumentAttachmentService."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTask, ScraperTaskType


@pytest.fixture
def service():
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService

    return DocumentAttachmentService(
        case_service=MagicMock(),
        renamer=MagicMock(),
    )


@pytest.fixture
def court_sms(db):
    return CourtSMS.objects.create(
        content="测试短信",
        received_at=timezone.now(),
        status=CourtSMSStatus.RENAMING,
    )


@pytest.mark.django_db
class TestGetPathsForRenaming:
    def test_no_scraper_task(self, service, court_sms):
        court_sms.scraper_task = None
        court_sms.save()
        assert service.get_paths_for_renaming(court_sms) == []

    def test_from_task_result(self, service, court_sms, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [str(doc)]},
        )
        court_sms.scraper_task = task
        court_sms.save()
        paths = service.get_paths_for_renaming(court_sms)
        assert len(paths) == 1


@pytest.mark.django_db
class TestPathsFromTaskResult:
    def test_no_scraper_task(self, service, court_sms):
        court_sms.scraper_task = None
        court_sms.save()
        assert service._paths_from_task_result(court_sms) == []

    def test_no_result(self, service, court_sms):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result=None,
        )
        court_sms.scraper_task = task
        court_sms.save()
        assert service._paths_from_task_result(court_sms) == []

    def test_with_files(self, service, court_sms, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [str(doc)]},
        )
        court_sms.scraper_task = task
        court_sms.save()
        paths = service._paths_from_task_result(court_sms)
        assert len(paths) == 1

    def test_nonexistent_files(self, service, court_sms):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": ["/nonexistent/file.pdf"]},
        )
        court_sms.scraper_task = task
        court_sms.save()
        paths = service._paths_from_task_result(court_sms)
        assert len(paths) == 0


@pytest.mark.django_db
class TestPathsFromSmsReference:
    def test_empty_list(self, service, court_sms):
        court_sms.document_file_paths = []
        court_sms.save()
        assert service._paths_from_sms_reference(court_sms) == []

    def test_with_valid_paths(self, service, court_sms, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        court_sms.document_file_paths = [str(doc)]
        court_sms.save()
        paths = service._paths_from_sms_reference(court_sms)
        assert len(paths) == 1

    def test_nonexistent_path(self, service, court_sms):
        court_sms.document_file_paths = ["/nonexistent/doc.pdf"]
        court_sms.save()
        paths = service._paths_from_sms_reference(court_sms)
        assert len(paths) == 0

    def test_non_list_skips(self, service, court_sms):
        court_sms.document_file_paths = "not_a_list"
        court_sms.save()
        assert service._paths_from_sms_reference(court_sms) == []


@pytest.mark.django_db
class TestCollectUniquePaths:
    def test_deduplicates(self, service, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        seen: set[str] = set()
        target: list[str] = []
        result = service._collect_unique_paths([str(doc), str(doc)], seen, target)
        assert len(result) == 1
        assert len(target) == 1

    def test_skips_nonexistent(self, service):
        seen: set[str] = set()
        target: list[str] = []
        result = service._collect_unique_paths(["/nonexistent/file.pdf"], seen, target)
        assert len(result) == 0

    def test_skips_empty_string(self, service):
        seen: set[str] = set()
        target: list[str] = []
        result = service._collect_unique_paths([""], seen, target)
        assert len(result) == 0

    def test_without_target(self, service, tmp_path):
        doc = tmp_path / "doc.pdf"
        doc.write_bytes(b"test")
        seen: set[str] = set()
        result = service._collect_unique_paths([str(doc)], seen)
        assert len(result) == 1


@pytest.mark.django_db
class TestRenameDocuments:
    def test_empty_paths(self, service):
        sms = MagicMock()
        assert service.rename_documents(sms, []) == []

    def test_renames_files(self, service, tmp_path):
        doc = tmp_path / "original.pdf"
        doc.write_bytes(b"test")
        sms = MagicMock()
        sms.id = 1
        sms.case = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at = timezone.now()
        service.renamer.rename_with_fallback.return_value = str(tmp_path / "renamed.pdf")
        (tmp_path / "renamed.pdf").write_bytes(b"test")

        result = service.rename_documents(sms, [str(doc)])
        assert len(result) == 1

    def test_renaming_failure_keeps_original(self, service, tmp_path):
        doc = tmp_path / "original.pdf"
        doc.write_bytes(b"test")
        sms = MagicMock()
        sms.id = 1
        sms.case = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at = timezone.now()
        service.renamer.rename_with_fallback.side_effect = Exception("rename failed")

        result = service.rename_documents(sms, [str(doc)])
        assert len(result) == 1
        assert result[0] == str(doc)

    def test_nonexistent_file_skips(self, service):
        sms = MagicMock()
        sms.id = 1
        sms.case = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at = timezone.now()
        result = service.rename_documents(sms, ["/nonexistent/file.pdf"])
        assert len(result) == 0


@pytest.mark.django_db
class TestGetPathsForNotification:
    def test_empty(self, service, court_sms):
        paths = service.get_paths_for_notification(court_sms)
        assert isinstance(paths, list)

    def test_from_renamed_files(self, service, court_sms, tmp_path):
        doc = tmp_path / "renamed.pdf"
        doc.write_bytes(b"test")
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"renamed_files": [str(doc)]},
        )
        court_sms.scraper_task = task
        court_sms.save()
        paths = service.get_paths_for_notification(court_sms)
        assert len(paths) == 1


@pytest.mark.django_db
class TestAddToCaseLog:
    def test_no_case_log(self, service, court_sms):
        court_sms.case_log = None
        result = service.add_to_case_log(court_sms, ["/path.pdf"])
        assert result is False

    def test_no_paths_with_mock(self, service):
        sms = MagicMock()
        sms.case_log = MagicMock()
        result = service.add_to_case_log(sms, [])
        assert result is False


@pytest.mark.django_db
class TestSanitizeFilename:
    def test_removes_illegal_chars(self, service):
        result = service._sanitize_filename_part('test<>:"|?*\\/file')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "*" not in result

    def test_removes_parentheses(self, service):
        result = service._sanitize_filename_part("test (value)")
        assert "(" not in result
        assert ")" not in result

    def test_strips_dots_and_spaces(self, service):
        result = service._sanitize_filename_part("  test  ")
        assert result == "test"

    def test_empty_string(self, service):
        assert service._sanitize_filename_part("") == ""

    def test_none_returns_empty(self, service):
        assert service._sanitize_filename_part(None) == ""


@pytest.mark.django_db
class TestFixFilenameFormat:
    def test_fixes_filename(self, service):
        """Test with a plain MagicMock SMS (not saved to DB)."""
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case.name = "张某诉李某案"
        sms.received_at = timezone.now()
        result = service.fix_filename_format("判决书.pdf", sms)
        assert result.endswith(".pdf")

    def test_fallback_for_unknown(self, service):
        sms = MagicMock()
        sms.case = None
        sms.received_at = timezone.now()
        result = service.fix_filename_format("random_file.pdf", sms)
        assert result.endswith(".pdf")
        assert "未知案件" in result

    def test_handles_exception(self, service):
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case.name = "测试"
        sms.received_at = timezone.now()
        result = service.fix_filename_format("file.pdf", sms)
        assert result.endswith(".pdf")


@pytest.mark.django_db
class TestGetUniqueFilepath:
    def test_unique_path(self, service, tmp_path):
        target = str(tmp_path)
        path, name = service._get_unique_filepath(target, "test.pdf")
        assert path.startswith(target)
        assert name == "test.pdf"


@pytest.mark.django_db
class TestFindRenamedFile:
    def test_no_path(self, service, court_sms):
        assert service._find_renamed_file("", court_sms) is None

    def test_no_case(self, service, court_sms):
        court_sms.case = None
        assert service._find_renamed_file("/some/path.pdf", court_sms) is None
