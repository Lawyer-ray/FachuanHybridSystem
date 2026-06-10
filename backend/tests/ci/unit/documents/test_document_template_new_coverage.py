"""
Tests for documents/services/document_template/ - validation_service, placeholder_extractor, repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path as RealPath

import pytest

from apps.core.exceptions import ValidationException


class TestDocumentTemplateValidationService:
    def _make_service(self):
        from apps.documents.services.document_template.validation_service import (
            DocumentTemplateValidationService,
        )

        return DocumentTemplateValidationService()

    def test_normalize_file_path_none(self):
        svc = self._make_service()
        assert svc.normalize_file_path(None) is None

    def test_normalize_file_path_strips(self):
        svc = self._make_service()
        assert svc.normalize_file_path("  path  ") == "path"

    def test_validate_file_path_empty(self):
        svc = self._make_service()
        assert svc.validate_file_path("") is False
        assert svc.validate_file_path("  ") is False

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_validate_file_path_valid(self, mock_resolve):
        mock_path = MagicMock()
        mock_path.is_file.return_value = True
        mock_resolve.return_value = mock_path
        svc = self._make_service()
        assert svc.validate_file_path("test.docx") is True

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_validate_file_path_value_error(self, mock_resolve):
        mock_resolve.side_effect = ValueError("bad path")
        svc = self._make_service()
        assert svc.validate_file_path("bad/path") is False

    def test_require_single_source_neither_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="必须提供"):
            svc.require_single_source(file=None, file_path=None)

    def test_require_single_source_both_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="不能同时"):
            svc.require_single_source(file=MagicMock(), file_path="path")

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_require_single_source_file_path_valid(self, mock_resolve):
        mock_path = MagicMock()
        mock_path.is_file.return_value = True
        mock_resolve.return_value = mock_path
        svc = self._make_service()
        result = svc.require_single_source(file=None, file_path="  valid.docx  ")
        assert result == "valid.docx"

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_require_single_source_file_path_invalid(self, mock_resolve):
        mock_resolve.side_effect = ValueError("bad")
        svc = self._make_service()
        with pytest.raises(ValidationException, match="路径无效"):
            svc.require_single_source(file=None, file_path="bad")

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_require_single_source_file_not_exists(self, mock_resolve):
        mock_path = MagicMock()
        mock_path.is_file.return_value = False
        mock_resolve.return_value = mock_path
        svc = self._make_service()
        with pytest.raises(ValidationException, match="不存在"):
            svc.require_single_source(file=None, file_path="missing.docx")

    def test_validate_update_file_source_both_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="不能同时"):
            svc.validate_update_file_source(file=MagicMock(), file_path="path")

    def test_validate_update_file_source_empty_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="不能为空"):
            svc.validate_update_file_source(file=None, file_path="  ")

    def test_validate_update_file_source_no_change(self):
        svc = self._make_service()
        result = svc.validate_update_file_source(file=None, file_path=None)
        assert result is None

    @patch("apps.documents.services.document_template.validation_service.resolve_docx_template_path")
    def test_validate_update_file_source_path_valid(self, mock_resolve):
        mock_path = MagicMock()
        mock_path.is_file.return_value = True
        mock_resolve.return_value = mock_path
        svc = self._make_service()
        result = svc.validate_update_file_source(file=None, file_path="valid.docx")
        assert result == "valid.docx"


class TestPlaceholderExtractor:
    def test_pattern_matches(self):
        import re

        from apps.documents.services.document_template.placeholder_extractor import (
            PLACEHOLDER_PATTERN,
        )

        text = "{{ case_name }} 和 {{defendant}} 以及 {{原告.姓名}}"
        matches = PLACEHOLDER_PATTERN.findall(text)
        assert "case_name" in matches
        assert "defendant" in matches

    def test_pattern_no_match(self):
        import re

        from apps.documents.services.document_template.placeholder_extractor import (
            PLACEHOLDER_PATTERN,
        )

        text = "No placeholders here"
        matches = PLACEHOLDER_PATTERN.findall(text)
        assert len(matches) == 0


class TestDocumentTemplateRepo:
    @pytest.mark.django_db
    def test_get_nonexistent(self):
        from apps.documents.services.document_template.repo import DocumentTemplateRepo

        repo = DocumentTemplateRepo()
        assert repo.get_optional(999999) is None

    @pytest.mark.django_db
    def test_get_nonexistent_raises(self):
        from apps.documents.models import DocumentTemplate
        from apps.documents.services.document_template.repo import DocumentTemplateRepo

        repo = DocumentTemplateRepo()
        with pytest.raises(DocumentTemplate.DoesNotExist):
            repo.get_by_id(999999)

    @pytest.mark.django_db
    def test_filter_empty(self):
        from apps.documents.services.document_template.repo import DocumentTemplateRepo

        repo = DocumentTemplateRepo()
        result = repo.filter(name="nonexistent_name_12345")
        assert list(result) == []


class TestFolderTemplateRepo:
    @pytest.mark.django_db
    def test_get_nonexistent(self):
        from apps.documents.services.folder_template.repo import FolderTemplateRepo

        repo = FolderTemplateRepo()
        assert repo.get_optional(999999) is None

    @pytest.mark.django_db
    def test_get_nonexistent_raises(self):
        from apps.documents.models import FolderTemplate
        from apps.documents.services.folder_template.repo import FolderTemplateRepo

        repo = FolderTemplateRepo()
        with pytest.raises(FolderTemplate.DoesNotExist):
            repo.get_by_id(999999)


class TestFolderTemplateStructureRules:
    def _make_rules(self, internal_dup=None, global_dup=None):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService
        from apps.documents.services.folder_template.structure_rules import (
            FolderTemplateStructureRules,
        )

        id_service = MagicMock(spec=FolderTemplateIdService)
        id_service.collect_structure_ids.return_value = {"a", "b"}
        id_service.find_internal_duplicates.return_value = internal_dup or set()
        id_service.find_global_duplicates.return_value = global_dup or set()
        return FolderTemplateStructureRules(id_service=id_service)

    def test_validate_empty_structure(self):
        rules = self._make_rules()
        fixed, msgs = rules.validate_structure_ids({})
        assert fixed is True
        assert msgs == []

    def test_validate_no_duplicates(self):
        rules = self._make_rules()
        fixed, msgs = rules.validate_structure_ids({"id": "root"})
        assert fixed is True
        assert msgs == []

    def test_validate_internal_duplicates(self):
        rules = self._make_rules(internal_dup={"a"})
        fixed, msgs = rules.validate_structure_ids({"id": "root"})
        assert fixed is False
        assert len(msgs) == 1

    def test_validate_global_duplicates(self):
        rules = self._make_rules(global_dup={"b"})
        fixed, msgs = rules.validate_structure_ids({"id": "root"})
        assert fixed is False
        assert len(msgs) == 1

    def test_validate_and_fix_no_duplicates(self):
        rules = self._make_rules()
        was_fixed, structure, msgs = rules.validate_and_fix_structure_ids({"id": "root"})
        assert was_fixed is False

    def test_validate_and_fix_with_duplicates(self):
        rules = self._make_rules(internal_dup={"a"})
        was_fixed, structure, msgs = rules.validate_and_fix_structure_ids({"id": "root"})
        assert was_fixed is True
        assert len(msgs) == 1

    def test_validate_and_fix_empty_structure(self):
        rules = self._make_rules()
        was_fixed, structure, msgs = rules.validate_and_fix_structure_ids({})
        assert was_fixed is False
