"""Document attachment service tests with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService


class TestDocumentAttachmentService:
    def _make(self, **kwargs):
        return DocumentAttachmentService(
            case_service=kwargs.get("case_service"),
            renamer=kwargs.get("renamer"),
        )

    def test_init_defaults(self):
        svc = self._make()
        assert svc._case_service is None
        assert svc._renamer is None

    def test_init_with_injection(self):
        mock_case = MagicMock()
        mock_renamer = MagicMock()
        svc = self._make(case_service=mock_case, renamer=mock_renamer)
        assert svc.case_service is mock_case
        assert svc.renamer is mock_renamer

    def test_get_paths_for_renaming_no_scraper_task(self):
        svc = self._make()
        sms = MagicMock()
        sms.scraper_task = None
        result = svc.get_paths_for_renaming(sms)
        assert result == []

    def test_get_paths_for_renaming_no_documents(self):
        svc = self._make()
        sms = MagicMock()
        sms.scraper_task.documents.filter.return_value = []
        sms.scraper_task.result = None
        result = svc.get_paths_for_renaming(sms)
        assert isinstance(result, list)

    def test_get_paths_for_notification_no_scraper(self):
        svc = self._make()
        sms = MagicMock()
        sms.scraper_task = None
        sms.document_file_paths = []
        result = svc.get_paths_for_notification(sms)
        assert isinstance(result, list)

    def test_rename_documents_empty(self):
        svc = self._make()
        sms = MagicMock()
        result = svc.rename_documents(sms, [])
        assert result == []

    def test_rename_documents_with_files(self):
        mock_renamer = MagicMock()
        mock_renamer.rename_with_fallback.return_value = "/tmp/renamed.pdf"
        svc = self._make(renamer=mock_renamer)

        sms = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock()

        with patch("apps.automation.services.sms.document_attachment_service.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.name = "original.pdf"
            mock_path.return_value = mock_path_instance
            result = svc.rename_documents(sms, ["/tmp/original.pdf"])
        assert isinstance(result, list)

    def test_add_to_case_log_no_log(self):
        svc = self._make()
        sms = MagicMock()
        sms.case_log = None
        result = svc.add_to_case_log(sms, ["/tmp/file.pdf"])
        assert result is False

    def test_add_to_case_log_no_files(self):
        svc = self._make()
        sms = MagicMock()
        sms.case_log = MagicMock()
        result = svc.add_to_case_log(sms, [])
        assert result is False

    def test_sanitize_filename_part(self):
        svc = self._make()
        assert svc._sanitize_filename_part("test<>file") == "testfile"
        assert svc._sanitize_filename_part("") == ""
        assert svc._sanitize_filename_part(None) == ""
        assert svc._sanitize_filename_part("  hello  ") == "hello"

    @patch("apps.automation.services.sms.document_attachment_service.FilenameTemplateService")
    def test_fix_filename_format(self, mock_fts):
        mock_fts.render_court_doc.return_value = "判决书（测试案件）_20240101收"
        svc = self._make()
        sms = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock(strftime=MagicMock(return_value="20240101"))
        result = svc.fix_filename_format("判决书.pdf", sms)
        assert isinstance(result, str)
        assert result.endswith(".pdf")

    @patch("apps.automation.services.sms.document_attachment_service.FilenameTemplateService")
    def test_fix_filename_format_no_title_match(self, mock_fts):
        mock_fts.render_court_doc.return_value = "司法文书（测试案件）_20240101收"
        svc = self._make()
        sms = MagicMock()
        sms.case.name = "测试案件"
        sms.received_at.date.return_value = MagicMock(strftime=MagicMock(return_value="20240101"))
        result = svc.fix_filename_format("random_file.pdf", sms)
        assert isinstance(result, str)
        assert result.endswith(".pdf")

    def test_collect_unique_paths(self):
        svc = self._make()
        seen = set()
        target = []
        with patch("apps.automation.services.sms.document_attachment_service.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.resolve.return_value = Path("/tmp/file.pdf")
            mock_path.return_value = mock_path_instance
            added = svc._collect_unique_paths(["/tmp/file.pdf"], seen, target)
        assert isinstance(added, list)

    def test_paths_from_sms_reference_no_list(self):
        svc = self._make()
        sms = MagicMock()
        sms.document_file_paths = None
        result = svc._paths_from_sms_reference(sms)
        assert result == []

    def test_paths_from_task_result_no_result(self):
        svc = self._make()
        sms = MagicMock()
        sms.scraper_task.result = None
        result = svc._paths_from_task_result(sms)
        assert result == []

    def test_find_renamed_file_no_path(self):
        svc = self._make()
        sms = MagicMock()
        result = svc._find_renamed_file("", sms)
        assert result is None

    def test_find_renamed_file_no_case_name(self):
        svc = self._make()
        sms = MagicMock()
        sms.case = None
        result = svc._find_renamed_file("/tmp/file.pdf", sms)
        assert result is None
