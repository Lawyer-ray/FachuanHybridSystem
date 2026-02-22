"""Business workflow orchestration."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from typing import Any

from django.db import transaction

from apps.core.exceptions import ValidationException
from apps.documents.models import DocumentTemplate
from apps.documents.services.document_template.repo import DocumentTemplateRepo
from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService


class DocumentTemplateWorkflow:
    def __init__(
        self, repo: DocumentTemplateRepo | None = None, validator: DocumentTemplateValidationService | None = None
    ) -> None:
        self._repo = repo
        self._validator = validator

    @property
    def repo(self) -> DocumentTemplateRepo:
        if self._repo is None:
            self._repo = DocumentTemplateRepo()
        return self._repo

    @property
    def validator(self) -> DocumentTemplateValidationService:
        if self._validator is None:
            self._validator = DocumentTemplateValidationService()
        return self._validator

    def create_template(
        self,
        name: str,
        template_type: str,
        file: Any | None = None,
        file_path: str | None = None,
        description: str = "",
        case_types: list[str] | None = None,
        case_stages: list[str] | None = None,
        contract_types: list[str] | None = None,
        contract_sub_type: str | None = None,
        is_active: bool = True,
    ) -> DocumentTemplate:
        normalized_file_path = self.validator.require_single_source(file, file_path)
        return self.repo.create(
            name=name,
            template_type=template_type,
            contract_sub_type=contract_sub_type,
            file=file,
            file_path=normalized_file_path or "",
            description=description,
            case_types=case_types or [],
            case_stages=case_stages or [],
            contract_types=contract_types or [],
            is_active=is_active,
        )

    def update_template(
        self,
        template: DocumentTemplate,
        name: str | None = None,
        template_type: str | None = None,
        contract_sub_type: str | None = None,
        file: Any | None = None,
        file_path: str | None = None,
        description: str | None = None,
        case_types: list[str] | None = None,
        case_stages: list[str] | None = None,
        contract_types: list[str] | None = None,
        is_active: bool | None = None,
        created_by: Any | None = None,
    ) -> DocumentTemplate:
        normalized_file_path = self.validator.validate_update_file_source(file, file_path)
        with transaction.atomic():
            _SIMPLE_FIELDS = {
                "name": name,
                "template_type": template_type,
                "contract_sub_type": contract_sub_type,
                "description": description,
                "case_types": case_types,
                "case_stages": case_stages,
                "contract_types": contract_types,
                "is_active": is_active,
            }
            for attr, value in _SIMPLE_FIELDS.items():
                if value is not None:
                    setattr(template, attr, value)
            if file is not None:
                template.file = file
                template.file_path = ""
            if file_path is not None:
                template.file_path = normalized_file_path or ""
                template.file = None
            template.save()
            self._clear_template_cache()
        return template

    def create_from_dict(self, data: dict[str, Any]) -> DocumentTemplate:
        file_path = data.get("file_path")
        if file_path and (not self.validator.validate_file_path(file_path)):
            raise ValidationException(
                message=_("文件不存在: %(p)s") % {"p": file_path},
                code="INVALID_FILE_PATH",
                errors={"file_path": f"文件不存在: {file_path}"},
            )
        return self.repo.create(
            name=data.get("name"),
            description=data.get("description", ""),
            template_type=data.get("template_type", "contract"),
            file_path=file_path or "",
            case_types=data.get("case_types", []),
            case_stages=data.get("case_stages", []),
            contract_types=data.get("contract_types", []),
            is_active=data.get("is_active", True),
        )

    def update_from_dict(self, template: DocumentTemplate, data: dict[str, Any]) -> DocumentTemplate:
        file_path = data.get("file_path")
        if file_path is not None:
            if file_path and (not self.validator.validate_file_path(file_path)):
                raise ValidationException(
                    message=_("文件不存在: %(p)s") % {"p": file_path},
                    code="INVALID_FILE_PATH",
                    errors={"file_path": f"文件不存在: {file_path}"},
                )
            template.file_path = file_path
        if data.get("name") is not None:
            template.name = data["name"]
        if data.get("description") is not None:
            template.description = data["description"]
        if data.get("template_type") is not None:
            template.template_type = data["template_type"]
        if data.get("case_types") is not None:
            template.case_types = data["case_types"]
        if data.get("case_stages") is not None:
            template.case_stages = data["case_stages"]
        if data.get("contract_types") is not None:
            template.contract_types = data["contract_types"]
        if data.get("is_active") is not None:
            template.is_active = data["is_active"]
        template.save()
        self._clear_template_cache()
        return template

    def _clear_template_cache(self) -> None:
        """清除文档模板缓存"""
        from apps.core.infrastructure import CacheKeys, CacheTimeout, bump_cache_version

        bump_cache_version(CacheKeys.documents_matching_version_document_templates(), timeout=CacheTimeout.get_day())
