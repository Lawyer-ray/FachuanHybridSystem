"""Tests for documents/services/folder_template/command_service.py — full branch coverage.

Covers: FolderTemplateCommandService create/update/delete/get_template_or_404.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


class TestFolderTemplateCommandServiceCreateTemplate:
    @pytest.mark.django_db
    def test_create_success(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (True, [])
        mock_repo.create.return_value = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        result = svc.create_template(
            name="test",
            case_type="civil",
            case_stage="trial",
            structure={"nodes": []},
        )
        assert result is not None

    @pytest.mark.django_db
    def test_create_validation_fails(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (False, "结构无效")
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(ValidationException) as exc_info:
            svc.create_template(
                name="test",
                case_type="civil",
                case_stage="trial",
                structure={"nodes": []},
            )
        assert "结构无效" in str(exc_info.value.message)

    @pytest.mark.django_db
    def test_create_structure_ids_fails(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (False, {"id_dup": "重复"})
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(ValidationException):
            svc.create_template(
                name="test",
                case_type="civil",
                case_stage="trial",
                structure={"nodes": []},
            )


class TestFolderTemplateCommandServiceUpdateStructure:
    @pytest.mark.django_db
    def test_update_success(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (True, [])
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with patch.object(FolderTemplateCommandService, '_clear_folder_template_cache'):
            result = svc.update_structure(template_id=1, structure={"nodes": []})
            assert result is mock_template

    @pytest.mark.django_db
    def test_update_not_found(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        from apps.documents.models import FolderTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = FolderTemplate.DoesNotExist()
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(NotFoundError):
            svc.update_structure(template_id=999, structure={"nodes": []})

    @pytest.mark.django_db
    def test_update_validation_fails(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (False, "无效结构")
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(ValidationException):
            svc.update_structure(template_id=1, structure={"nodes": []})

    @pytest.mark.django_db
    def test_update_structure_ids_fails(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (False, {"dup": "dup"})
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(ValidationException):
            svc.update_structure(template_id=1, structure={"nodes": []})


class TestFolderTemplateCommandServiceDeleteTemplate:
    @pytest.mark.django_db
    def test_delete_success(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_template.is_active = True
        mock_repo.get_by_id.return_value = mock_template
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with patch.object(FolderTemplateCommandService, '_clear_folder_template_cache'):
            result = svc.delete_template(template_id=1)
            assert result is True
            assert mock_template.is_active is False

    @pytest.mark.django_db
    def test_delete_not_found(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        from apps.documents.models import FolderTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = FolderTemplate.DoesNotExist()
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(NotFoundError):
            svc.delete_template(template_id=999)


class TestFolderTemplateCommandServiceCreateFromDict:
    @pytest.mark.django_db
    def test_create_from_dict(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (True, [])
        mock_repo.create.return_value = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        result = svc.create_template_from_dict(data={
            "name": "template",
            "case_type": "civil",
            "case_stage": "trial",
            "structure": {"nodes": []},
            "is_default": True,
            "is_active": True,
        })
        assert result is not None

    @pytest.mark.django_db
    def test_create_from_dict_with_extra_fields(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (True, [])
        mock_repo.create.return_value = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        result = svc.create_template_from_dict(data={
            "name": "template2",
            "case_type": "criminal",
            "case_stage": "investigation",
            "structure": {"nodes": []},
            "template_type": "contract",
            "case_types": ["criminal"],
            "case_stages": ["investigation"],
            "contract_types": ["labor"],
        })
        assert result is not None


class TestFolderTemplateCommandServiceUpdateFromDict:
    @pytest.mark.django_db
    def test_update_with_structure(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_validation.validate_structure.return_value = (True, "")
        mock_rules = MagicMock()
        mock_rules.validate_structure_ids.return_value = (True, [])
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with patch.object(FolderTemplateCommandService, '_clear_folder_template_cache'):
            result = svc.update_template_from_dict(
                template_id=1,
                data={"structure": {"nodes": []}, "name": "updated"},
            )
            assert result is not None

    @pytest.mark.django_db
    def test_update_without_structure(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        result = svc.update_template_from_dict(
            template_id=1,
            data={"name": "updated_name"},
        )
        assert result is not None

    @pytest.mark.django_db
    def test_update_template_not_found(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        from apps.documents.models import FolderTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = FolderTemplate.DoesNotExist()
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(NotFoundError):
            svc.update_template_from_dict(template_id=999, data={"name": "x"})


class TestFolderTemplateCommandServiceGetTemplateOr404:
    @pytest.mark.django_db
    def test_found(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        mock_repo = MagicMock()
        mock_template = MagicMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        assert svc.get_template_or_404(1) is mock_template

    @pytest.mark.django_db
    def test_not_found(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService
        from apps.documents.models import FolderTemplate
        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = FolderTemplate.DoesNotExist()
        mock_validation = MagicMock()
        mock_rules = MagicMock()
        svc = FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_rules,
        )
        with pytest.raises(NotFoundError):
            svc.get_template_or_404(999)
