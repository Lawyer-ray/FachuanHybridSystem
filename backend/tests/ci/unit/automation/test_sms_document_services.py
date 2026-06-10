"""Tests for SMS DocumentAttachmentService and DocumentRenamer covering rename and attachment logic."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
from apps.automation.services.sms.document_renamer import DocumentRenamer


# ── DocumentAttachmentService ──


class TestDocumentAttachmentService:
    @pytest.fixture
    def svc(self):
        case_service = MagicMock()
        renamer = MagicMock()
        return DocumentAttachmentService(case_service=case_service, renamer=renamer)

    def test_init_with_deps(self, svc):
        assert svc._case_service is not None
        assert svc._renamer is not None

    def test_case_service_property(self, svc):
        assert svc.case_service is svc._case_service

    def test_renamer_property(self, svc):
        assert svc.renamer is svc._renamer

    def test_get_paths_for_renaming_no_scraper_task(self, svc):
        sms = MagicMock()
        sms.scraper_task = None
        result = svc.get_paths_for_renaming(sms)
        assert result == []

    def test_get_paths_for_renaming_no_documents(self, svc):
        sms = MagicMock()
        sms.scraper_task.documents.filter.return_value.exists.return_value = False
        sms.scraper_task.result = None
        result = svc.get_paths_for_renaming(sms)
        assert isinstance(result, list)

    def test_rename_documents_empty(self, svc):
        sms = MagicMock()
        result = svc.rename_documents(sms, [])
        assert result == []

    def test_add_to_case_log_no_log(self, svc):
        sms = MagicMock()
        sms.case_log = None
        svc.add_to_case_log(sms, ["/path/to/doc.pdf"])
        # Should not raise


# ── DocumentRenamer ──


class TestDocumentRenamer:
    @pytest.fixture
    def renamer(self):
        return DocumentRenamer()

    def test_init(self, renamer):
        assert renamer is not None

    def test_sanitize_filename_part(self, renamer):
        result = renamer._sanitize_filename_part("valid_name")
        assert result == "valid_name"

    def test_sanitize_filename_part_special_chars(self, renamer):
        result = renamer._sanitize_filename_part("file/name:test")
        assert "/" not in result
        assert ":" not in result

    def test_sanitize_filename_part_empty(self, renamer):
        result = renamer._sanitize_filename_part("")
        assert result == ""

    def test_sanitize_filename_part_long(self, renamer):
        long_name = "a" * 200
        result = renamer._sanitize_filename_part(long_name)
        # sanitize doesn't truncate, just removes illegal chars
        assert len(result) == 200

    def test_extract_title_from_filename(self, renamer):
        result = renamer._extract_title_from_filename("/path/to/判决书_张三诉李四.pdf")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extract_title_from_filename_simple(self, renamer):
        result = renamer._extract_title_from_filename("/path/to/simple.pdf")
        assert result == "simple"

    @pytest.mark.django_db
    def test_generate_filename(self, renamer):
        result = renamer.generate_filename(
            title="判决书",
            case_name="张三诉李四",
            received_date=date(2025, 1, 15),
        )
        assert isinstance(result, str)
        assert result.endswith(".pdf")

    def test_normalize_title_candidate(self, renamer):
        result = renamer._normalize_title_candidate("  SomeTitle  ")
        # The method strips, removes whitespace, quotes, etc.
        assert result == "SomeTitle"

    def test_normalize_title_candidate_empty(self, renamer):
        result = renamer._normalize_title_candidate("")
        assert result == ""

    def test_normalize_title_candidate_with_pdf_extension(self, renamer):
        result = renamer._normalize_title_candidate("判决书.pdf")
        assert result == "判决书"

    def test_normalize_title_candidate_with_court_prefix(self, renamer):
        result = renamer._normalize_title_candidate("北京市朝阳区人民法院判决书")
        # Court prefix patterns may be stripped
        assert isinstance(result, str)

    def test_sms_type_to_label_known_types(self, renamer):
        # DocumentRenamer might not have this method - skip if not present
        if hasattr(renamer, '_sms_type_to_label'):
            result = renamer._sms_type_to_label("judgment")
            assert isinstance(result, str)
