"""Tests for documents/services/template/template_service.py — full branch coverage.

Covers: DocumentTemplateService create/update/validate/extract/delete/get_all methods.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.exceptions import NotFoundError


class TestDocumentTemplateServiceInit:
    def test_default_init(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        assert svc._repo is None
        assert svc._validator is None
        assert svc._workflow is None

    def test_injected_init(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_val = MagicMock()
        mock_wf = MagicMock()
        svc = DocumentTemplateService(repo=mock_repo, validator=mock_val, workflow=mock_wf)
        assert svc.repo is mock_repo
        assert svc.validator is mock_val
        assert svc.workflow is mock_wf


class TestDocumentTemplateServiceRepo:
    def test_repo_lazy_load(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        with patch("apps.documents.services.template.template_service.DocumentTemplateRepo") as MockRepo:
            MockRepo.return_value = MagicMock()
            repo = svc.repo
            MockRepo.assert_called_once()
            assert repo is svc._repo

    def test_validator_lazy_load(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        with patch("apps.documents.services.template.template_service.DocumentTemplateValidationService") as MockVal:
            MockVal.return_value = MagicMock()
            v = svc.validator
            MockVal.assert_called_once()
            assert v is svc._validator

    def test_workflow_lazy_load(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        with patch("apps.documents.services.template.template_service.DocumentTemplateWorkflow") as MockWf:
            MockWf.return_value = MagicMock()
            w = svc.workflow
            MockWf.assert_called_once()
            assert w is svc._workflow


class TestDocumentTemplateServiceCreateTemplate:
    def test_create_template(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_workflow = MagicMock()
        mock_template = MagicMock()
        mock_workflow.create_template.return_value = mock_template
        svc = DocumentTemplateService(workflow=mock_workflow)
        result = svc.create_template(name="test", template_type="case", file=None)
        assert result is mock_template
        mock_workflow.create_template.assert_called_once()


class TestDocumentTemplateServiceUpdateTemplate:
    def test_update_success(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_workflow = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_workflow.update_template.return_value = mock_template
        svc = DocumentTemplateService(repo=mock_repo, workflow=mock_workflow)
        result = svc.update_template(template_id=1, name="new")
        assert result is mock_template

    def test_update_not_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = MagicMock(side_effect=type('DoesNotExist', (Exception,), {})())
        # Need actual DoesNotExist
        from apps.documents.models import DocumentTemplate
        mock_repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist()
        svc = DocumentTemplateService(repo=mock_repo)
        with pytest.raises(NotFoundError) as exc_info:
            svc.update_template(template_id=999)
        assert "模板不存在" in str(exc_info.value.message)


class TestDocumentTemplateServiceValidateFilePath:
    def test_empty_path(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        assert svc.validate_file_path("") is False
        assert svc.validate_file_path(None) is False

    def test_valid_path(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_validator = MagicMock()
        mock_validator.validate_file_path.return_value = True
        svc = DocumentTemplateService(validator=mock_validator)
        assert svc.validate_file_path("/path/to/file.docx") is True


class TestDocumentTemplateServiceGetFullFilePath:
    def test_file_exists(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.get_file_location.return_value = "/some/path.docx"
        mock_template.name = "test"
        mock_template.pk = 1
        with patch("apps.documents.services.template.template_service.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = svc.get_full_file_path(mock_template)
            assert result == "/some/path.docx"

    def test_file_not_exists(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.get_file_location.return_value = "/missing/path.docx"
        mock_template.name = "test"
        mock_template.pk = 1
        with patch("apps.documents.services.template.template_service.Path") as MockPath:
            MockPath.return_value.exists.return_value = False
            result = svc.get_full_file_path(mock_template)
            assert result is None

    def test_exception(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.get_file_location.side_effect = RuntimeError("io error")
        mock_template.name = "test"
        mock_template.pk = 1
        with pytest.raises(RuntimeError):
            svc.get_full_file_path(mock_template)


class TestDocumentTemplateServiceExtractPlaceholders:
    def test_file_not_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.name = "test"
        mock_template.pk = 1
        with patch.object(svc, 'get_full_file_path', return_value=None):
            assert svc.extract_placeholders(mock_template) == []

    def test_extraction_success(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.name = "test"
        mock_template.pk = 1
        with patch.object(svc, 'get_full_file_path', return_value="/path/to/doc.docx"):
            with patch("apps.documents.services.template.template_service.extract_placeholders_from_file") as mock_extract:
                mock_extract.return_value = ["name", "date"]
                result = svc.extract_placeholders(mock_template)
                assert result == ["name", "date"]

    def test_extraction_error(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        mock_template.name = "test"
        mock_template.pk = 1
        with patch.object(svc, 'get_full_file_path', return_value="/path/to/doc.docx"):
            with patch("apps.documents.services.template.template_service.extract_placeholders_from_file", side_effect=RuntimeError("parse error")):
                with pytest.raises(RuntimeError):
                    svc.extract_placeholders(mock_template)


class TestDocumentTemplateServiceGetUndefinedPlaceholders:
    def test_no_template_placeholders(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        with patch.object(svc, 'extract_placeholders', return_value=[]):
            assert svc.get_undefined_placeholders(mock_template) == []

    def test_with_undefined(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        svc = DocumentTemplateService()
        mock_template = MagicMock()
        with patch.object(svc, 'extract_placeholders', return_value=["key_a", "key_b"]):
            with patch("apps.documents.services.template.template_service.Placeholder") as MockPlaceholder:
                MockPlaceholder.objects.filter.return_value.values_list.return_value = ["key_a"]
                result = svc.get_undefined_placeholders(mock_template)
                assert "key_b" in result
                assert "key_a" not in result


class TestDocumentTemplateServiceGetTemplateById:
    def test_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        svc = DocumentTemplateService(repo=mock_repo)
        assert svc.get_template_by_id(1) is mock_template

    def test_not_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import DocumentTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist()
        svc = DocumentTemplateService(repo=mock_repo)
        with pytest.raises(NotFoundError):
            svc.get_template_by_id(999)


class TestDocumentTemplateServiceDeleteTemplate:
    def test_delete_success(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_template.is_active = True
        mock_repo.get_by_id.return_value = mock_template
        svc = DocumentTemplateService(repo=mock_repo)
        assert svc.delete_template(1) is True
        assert mock_template.is_active is False
        mock_template.save.assert_called_once()

    def test_delete_not_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import DocumentTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist()
        svc = DocumentTemplateService(repo=mock_repo)
        with pytest.raises(NotFoundError):
            svc.delete_template(999)


class TestDocumentTemplateServiceCreateFromDict:
    def test_create_from_dict(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_workflow = MagicMock()
        mock_template = MagicMock()
        mock_workflow.create_from_dict.return_value = mock_template
        svc = DocumentTemplateService(workflow=mock_workflow)
        result = svc.create_template_from_dict({"name": "test"})
        assert result is mock_template


class TestDocumentTemplateServiceUpdateFromDict:
    def test_update_from_dict_success(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        mock_repo = MagicMock()
        mock_workflow = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_workflow.update_from_dict.return_value = mock_template
        svc = DocumentTemplateService(repo=mock_repo, workflow=mock_workflow)
        result = svc.update_template_from_dict(1, {"name": "updated"})
        assert result is mock_template

    def test_update_from_dict_not_found(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import DocumentTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist()
        svc = DocumentTemplateService(repo=mock_repo)
        with pytest.raises(NotFoundError):
            svc.update_template_from_dict(999, {"name": "x"})
