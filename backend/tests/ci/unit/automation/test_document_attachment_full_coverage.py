"""Comprehensive tests for automation.services.sms.document_attachment_service.

Covers: get_paths_for_renaming, _paths_from_sms_reference, _paths_from_court_documents,
_paths_from_task_result, get_paths_for_notification, _collect_unique_paths,
rename_documents, fix_filename_format, _sanitize_filename_part,
_find_renamed_file, _get_unique_filepath, lazy properties.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestDocumentAttachmentService:
    """Test suite for DocumentAttachmentService."""

    def _svc(self, **kw):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService(**kw)


# ---------------------------------------------------------------------------
# get_paths_for_renaming
# ---------------------------------------------------------------------------


class TestGetPathsForRenaming:
    def _svc(self, **kw):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService(**kw)

    def test_no_scraper_task(self):
        sms = MagicMock()
        sms.id = 1
        sms.scraper_task = None
        svc = self._svc()
        assert svc.get_paths_for_renaming(sms) == []

    def test_uses_court_documents_first(self):
        sms = MagicMock()
        sms.id = 1
        svc = self._svc()
        svc._paths_from_court_documents = MagicMock(return_value=["/tmp/doc1.pdf"])
        result = svc.get_paths_for_renaming(sms)
        assert result == ["/tmp/doc1.pdf"]

    def test_falls_back_to_task_result(self):
        sms = MagicMock()
        sms.id = 1
        svc = self._svc()
        svc._paths_from_court_documents = MagicMock(return_value=[])
        svc._paths_from_task_result = MagicMock(return_value=["/tmp/doc2.pdf"])
        result = svc.get_paths_for_renaming(sms)
        assert result == ["/tmp/doc2.pdf"]

    def test_exception_returns_empty(self):
        sms = MagicMock()
        sms.id = 1
        svc = self._svc()
        svc._paths_from_court_documents = MagicMock(side_effect=RuntimeError("boom"))
        result = svc.get_paths_for_renaming(sms)
        assert result == []


# ---------------------------------------------------------------------------
# _paths_from_sms_reference
# ---------------------------------------------------------------------------


class TestPathsFromSmsReference:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_valid_paths(self):
        sms = MagicMock()
        sms.document_file_paths = ["/tmp/exists.pdf"]
        svc = self._svc()
        with patch.object(Path, "exists", return_value=True):
            result = svc._paths_from_sms_reference(sms)
        assert "/tmp/exists.pdf" in result

    def test_non_list_returns_empty(self):
        sms = MagicMock()
        sms.document_file_paths = "not a list"
        svc = self._svc()
        assert svc._paths_from_sms_reference(sms) == []

    def test_nonexistent_path_skipped(self):
        sms = MagicMock()
        sms.document_file_paths = ["/tmp/nonexistent.pdf"]
        svc = self._svc()
        with patch.object(Path, "exists", return_value=False):
            result = svc._paths_from_sms_reference(sms)
        assert result == []

    def test_empty_path_skipped(self):
        sms = MagicMock()
        sms.document_file_paths = ["", "/tmp/exists.pdf"]
        svc = self._svc()
        with patch.object(Path, "exists", return_value=True):
            result = svc._paths_from_sms_reference(sms)
        assert "" not in result


# ---------------------------------------------------------------------------
# _paths_from_court_documents
# ---------------------------------------------------------------------------


class TestPathsFromCourtDocuments:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_no_scraper_task(self):
        sms = MagicMock()
        sms.scraper_task = None
        svc = self._svc()
        assert svc._paths_from_court_documents(sms) == []

    def test_no_documents_attr(self):
        sms = MagicMock()
        sms.scraper_task = MagicMock(spec=[])  # no documents
        svc = self._svc()
        assert svc._paths_from_court_documents(sms) == []

    def test_with_documents(self):
        sms = MagicMock()
        doc = MagicMock()
        doc.download_status = "success"
        doc.local_file_path = "/tmp/doc.pdf"
        sms.scraper_task.documents.filter.return_value = [doc]
        svc = self._svc()
        with patch.object(Path, "exists", return_value=True):
            result = svc._paths_from_court_documents(sms)
        assert "/tmp/doc.pdf" in result

    def test_nonexistent_path_skipped(self):
        sms = MagicMock()
        doc = MagicMock()
        doc.download_status = "success"
        doc.local_file_path = "/tmp/missing.pdf"
        sms.scraper_task.documents.filter.return_value = [doc]
        svc = self._svc()
        with patch.object(Path, "exists", return_value=False):
            result = svc._paths_from_court_documents(sms)
        assert result == []


# ---------------------------------------------------------------------------
# _paths_from_task_result
# ---------------------------------------------------------------------------


class TestPathsFromTaskResult:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_no_scraper_task(self):
        sms = MagicMock()
        sms.scraper_task = None
        svc = self._svc()
        assert svc._paths_from_task_result(sms) == []

    def test_no_result(self):
        sms = MagicMock()
        sms.scraper_task.result = None
        svc = self._svc()
        assert svc._paths_from_task_result(sms) == []

    def test_non_dict_result(self):
        sms = MagicMock()
        sms.scraper_task.result = "string"
        svc = self._svc()
        assert svc._paths_from_task_result(sms) == []

    def test_with_valid_files(self):
        sms = MagicMock()
        sms.scraper_task.result = {"files": ["/tmp/file1.pdf", "/tmp/file2.pdf"]}
        svc = self._svc()
        with patch.object(Path, "exists", return_value=True):
            result = svc._paths_from_task_result(sms)
        assert len(result) == 2

    def test_nonexistent_files(self):
        sms = MagicMock()
        sms.scraper_task.result = {"files": ["/tmp/missing.pdf"]}
        svc = self._svc()
        with patch.object(Path, "exists", return_value=False):
            result = svc._paths_from_task_result(sms)
        assert result == []

    def test_empty_files(self):
        sms = MagicMock()
        sms.scraper_task.result = {"files": []}
        svc = self._svc()
        assert svc._paths_from_task_result(sms) == []


# ---------------------------------------------------------------------------
# get_paths_for_notification
# ---------------------------------------------------------------------------


class TestGetPathsForNotification:
    def _svc(self, **kw):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService(**kw)

    def test_uses_sms_reference(self):
        sms = MagicMock()
        sms.id = 1
        sms.scraper_task = None
        svc = self._svc()
        svc._paths_from_sms_reference = MagicMock(return_value=["/tmp/a.pdf"])
        svc._collect_unique_paths = MagicMock(side_effect=lambda paths, seen, target: target.extend(paths))
        result = svc.get_paths_for_notification(sms)
        assert "/tmp/a.pdf" in result

    def test_renamed_files_priority(self):
        sms = MagicMock()
        sms.id = 1
        sms.scraper_task = MagicMock()
        sms.scraper_task.result = {"renamed_files": ["/tmp/renamed.pdf"]}
        svc = self._svc()
        svc._paths_from_sms_reference = MagicMock(return_value=[])
        svc._collect_unique_paths = MagicMock(side_effect=lambda paths, seen, target: target.extend(paths))
        svc._collect_from_court_documents = MagicMock()
        result = svc.get_paths_for_notification(sms)
        assert "/tmp/renamed.pdf" in result

    def test_exception_returns_empty(self):
        sms = MagicMock()
        sms.id = 1
        svc = self._svc()
        svc._paths_from_sms_reference = MagicMock(side_effect=RuntimeError("boom"))
        result = svc.get_paths_for_notification(sms)
        assert result == []


# ---------------------------------------------------------------------------
# _collect_unique_paths
# ---------------------------------------------------------------------------


class TestCollectUniquePaths:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_unique_paths(self):
        svc = self._svc()
        seen: set[str] = set()
        target: list[str] = []
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "resolve", return_value=Path("/tmp/a.pdf")):
                result = svc._collect_unique_paths(["/tmp/a.pdf", "/tmp/a.pdf"], seen, target)
        assert len(target) == 1  # deduped

    def test_nonexistent_skipped(self):
        svc = self._svc()
        seen: set[str] = set()
        target: list[str] = []
        with patch.object(Path, "exists", return_value=False):
            result = svc._collect_unique_paths(["/tmp/missing.pdf"], seen, target)
        assert target == []

    def test_empty_path_skipped(self):
        svc = self._svc()
        seen: set[str] = set()
        target: list[str] = []
        result = svc._collect_unique_paths(["", None], seen, target)
        assert target == []

    def test_returns_added_list(self):
        svc = self._svc()
        seen: set[str] = set()
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "resolve", return_value=Path("/tmp/a.pdf")):
                result = svc._collect_unique_paths(["/tmp/a.pdf"], seen)
        assert len(result) == 1

    def test_no_target(self):
        svc = self._svc()
        seen: set[str] = set()
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "resolve", return_value=Path("/tmp/a.pdf")):
                result = svc._collect_unique_paths(["/tmp/a.pdf"], seen)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# rename_documents
# ---------------------------------------------------------------------------


class TestRenameDocuments:
    def _svc(self, **kw):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService(**kw)

    def test_empty_paths(self):
        sms = MagicMock()
        sms.id = 1
        svc = self._svc()
        assert svc.rename_documents(sms, []) == []

    def test_successful_rename(self):
        sms = MagicMock()
        sms.id = 1
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock()
        svc = self._svc()
        svc._renamer = MagicMock()
        svc._renamer.rename_with_fallback.return_value = "/tmp/renamed.pdf"
        with patch.object(Path, "exists", return_value=True):
            result = svc.rename_documents(sms, ["/tmp/original.pdf"])
        assert result == ["/tmp/renamed.pdf"]

    def test_nonexistent_file_skipped(self):
        sms = MagicMock()
        sms.id = 1
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock()
        svc = self._svc()
        svc._renamer = MagicMock()
        with patch.object(Path, "exists", return_value=False):
            result = svc.rename_documents(sms, ["/tmp/missing.pdf"])
        assert result == []

    def test_rename_exception_keeps_original(self):
        sms = MagicMock()
        sms.id = 1
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock()
        svc = self._svc()
        svc._renamer = MagicMock()
        svc._renamer.rename_with_fallback.side_effect = RuntimeError("boom")
        with patch.object(Path, "exists", return_value=True):
            result = svc.rename_documents(sms, ["/tmp/original.pdf"])
        assert result == ["/tmp/original.pdf"]

    def test_rename_exception_file_missing(self):
        sms = MagicMock()
        sms.id = 1
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock()
        svc = self._svc()
        svc._renamer = MagicMock()
        svc._renamer.rename_with_fallback.side_effect = RuntimeError("boom")
        with patch.object(Path, "exists", return_value=False):
            result = svc.rename_documents(sms, ["/tmp/missing.pdf"])
        assert result == []


# ---------------------------------------------------------------------------
# fix_filename_format
# ---------------------------------------------------------------------------


class TestFixFilenameFormat:
    def _svc(self, **kw):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService(**kw)

    def test_renders_title(self):
        sms = MagicMock()
        sms.case.name = "张三诉李四"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="判决书（张三诉李四）_20250101收"):
            result = svc.fix_filename_format("判决书.pdf", sms)
        assert result.endswith(".pdf")

    def test_matches_known_title_pattern(self):
        sms = MagicMock()
        sms.case.name = "测试"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            result = svc.fix_filename_format("受理案件通知书.pdf", sms)
        assert result.endswith(".pdf")

    def test_unknown_title_uses_sanitized_filename(self):
        sms = MagicMock()
        sms.case.name = "测试"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            result = svc.fix_filename_format("random_doc.pdf", sms)
        assert result.endswith(".pdf")

    def test_exception_fallback(self):
        sms = MagicMock()
        sms.case.name = "测试"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        sms.received_at.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="fallback"):
            # Trigger the except block by making sanitization raise
            with patch.object(svc, "_sanitize_filename_part", side_effect=[RuntimeError("boom"), "title"]):
                result = svc.fix_filename_format("doc.pdf", sms)
        assert result.endswith(".pdf")

    def test_case_name_truncated(self):
        sms = MagicMock()
        sms.case.name = "张" * 50
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            result = svc.fix_filename_format("判决书.pdf", sms)
        assert result.endswith(".pdf")

    def test_no_extension(self):
        sms = MagicMock()
        sms.case.name = "测试"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            result = svc.fix_filename_format("nodoctitle", sms)
        assert result.endswith(".pdf")

    def test_empty_title_fallback(self):
        sms = MagicMock()
        sms.case.name = "测试"
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            with patch.object(svc, "_sanitize_filename_part", return_value=""):
                result = svc.fix_filename_format(".pdf", sms)
        assert "司法文书" in result or result.endswith(".pdf")

    def test_no_case(self):
        sms = MagicMock()
        sms.case = None
        sms.received_at.date.return_value.strftime.return_value = "20250101"
        svc = self._svc()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.render_court_doc", return_value="result"):
            result = svc.fix_filename_format("判决书.pdf", sms)
        assert result.endswith(".pdf")


# ---------------------------------------------------------------------------
# _sanitize_filename_part
# ---------------------------------------------------------------------------


class TestSanitizeFilenamePart:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_removes_illegal_chars(self):
        svc = self._svc()
        result = svc._sanitize_filename_part('file<>:"|?*\\/name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_removes_english_parens(self):
        svc = self._svc()
        result = svc._sanitize_filename_part("file(name)test")
        assert "(" not in result
        assert ")" not in result

    def test_removes_control_chars(self):
        svc = self._svc()
        result = svc._sanitize_filename_part("file\x00\x01name")
        assert "\x00" not in result

    def test_strips_dots_and_spaces(self):
        svc = self._svc()
        result = svc._sanitize_filename_part("  file.  ")
        assert result == "file"

    def test_empty(self):
        svc = self._svc()
        assert svc._sanitize_filename_part("") == ""

    def test_none(self):
        svc = self._svc()
        assert svc._sanitize_filename_part(None) == ""

    def test_chinese_chars_preserved(self):
        svc = self._svc()
        result = svc._sanitize_filename_part("判决书")
        assert result == "判决书"


# ---------------------------------------------------------------------------
# _find_renamed_file
# ---------------------------------------------------------------------------


class TestFindRenamedFile:
    def _svc(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        return DocumentAttachmentService()

    def test_empty_path(self):
        svc = self._svc()
        assert svc._find_renamed_file("", MagicMock()) is None

    def test_no_case(self):
        svc = self._svc()
        sms = MagicMock()
        sms.case = None
        assert svc._find_renamed_file("/tmp/doc.pdf", sms) is None

    def test_no_case_name(self):
        svc = self._svc()
        sms = MagicMock()
        sms.case.name = ""
        assert svc._find_renamed_file("/tmp/doc.pdf", sms) is None

    @patch("glob.glob")
    def test_match_found(self, mock_glob):
        svc = self._svc()
        sms = MagicMock()
        sms.case.name = "张三诉李四纠纷案"
        mock_glob.return_value = ["/tmp/张三诉李四_20250101.pdf"]
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_mtime = 100
                result = svc._find_renamed_file("/tmp/original.pdf", sms)
        assert result == "/tmp/张三诉李四_20250101.pdf"

    @patch("glob.glob")
    def test_no_match(self, mock_glob):
        svc = self._svc()
        sms = MagicMock()
        sms.case.name = "张三诉李四纠纷案"
        mock_glob.return_value = []
        with patch.object(Path, "exists", return_value=True):
            result = svc._find_renamed_file("/tmp/original.pdf", sms)
        assert result is None

    def test_exception(self):
        svc = self._svc()
        sms = MagicMock()
        sms.case.name = "张三诉李四纠纷案"
        with patch("glob.glob", side_effect=RuntimeError("boom")):
            result = svc._find_renamed_file("/tmp/original.pdf", sms)
        assert result is None


# ---------------------------------------------------------------------------
# _get_unique_filepath
# ---------------------------------------------------------------------------


class TestGetUniqueFilepath:
    def test_delegates(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        svc = DocumentAttachmentService()
        with patch("apps.core.services.filename_template_service.FilenameTemplateService.get_unique_filepath", return_value=("/tmp/doc_1.pdf", "doc_1.pdf")):
            path, name = svc._get_unique_filepath("/tmp", "doc.pdf")
        assert path == "/tmp/doc_1.pdf"
        assert name == "doc_1.pdf"


# ---------------------------------------------------------------------------
# Lazy properties
# ---------------------------------------------------------------------------


class TestLazyProperties:
    def test_case_service_lazy(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        svc = DocumentAttachmentService()
        svc._case_service = None
        with patch("apps.core.dependencies.automation_sms_wiring.build_sms_case_service", return_value="cs"):
            assert svc.case_service == "cs"

    def test_renamer_lazy(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
        svc = DocumentAttachmentService()
        svc._renamer = None
        with patch("apps.automation.services.sms.document_renamer.DocumentRenamer", return_value="renamer"):
            assert svc.renamer == "renamer"
