"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

"\n文书模板服务\n\n提供文书模板的 CRUD 操作、文件路径验证、版本管理和占位符提取功能.\n"
"\nRequirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.9, 2.10\n"
import logging
from typing import Any, cast

from django.core.files.uploadedfile import UploadedFile

from apps.core.exceptions import NotFoundError
from apps.core.path import Path
from apps.documents.models import DocumentTemplate, Placeholder
from apps.documents.services.document_template.placeholder_extractor import (
    extract_placeholders as extract_placeholders_from_file,
)
from apps.documents.services.document_template.repo import DocumentTemplateRepo
from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
from apps.documents.services.document_template.workflow import DocumentTemplateWorkflow

logger = logging.getLogger(__name__)


class DocumentTemplateService:
    """
    文书模板服务

    负责文书模板的创建、更新、查询、版本管理和占位符提取.
    """

    def __init__(
        self,
        repo: DocumentTemplateRepo | None = None,
        validator: DocumentTemplateValidationService | None = None,
        workflow: DocumentTemplateWorkflow | None = None,
    ) -> None:
        self._repo = repo
        self._validator = validator
        self._workflow = workflow

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

    @property
    def workflow(self) -> DocumentTemplateWorkflow:
        if self._workflow is None:
            self._workflow = DocumentTemplateWorkflow(repo=self.repo, validator=self.validator)
        return self._workflow

    def create_template(
        self,
        name: str,
        template_type: str,
        file: UploadedFile | None = None,
        file_path: str | None = None,
        description: str = "",
        case_types: list[str] | None = None,
        case_stages: list[str] | None = None,
        contract_types: list[str] | None = None,
        contract_sub_type: str | None = None,
        is_active: bool = True,
    ) -> DocumentTemplate:
        """
        创建文书模板

        支持两种模式:
        1. 上传模式:通过 file 参数上传文件
        2. 路径引用模式:通过 file_path 指定已存在的文件路径

        Args:
            name: 模板名称
            template_type: 模板类型
            file: 上传的文件(上传模式)
            file_path: 文件路径(路径引用模式)
            description: 描述
            case_types: 适用案件类型列表
            case_stages: 适用案件阶段列表
            contract_types: 适用合同类型列表
            contract_sub_type: 合同子类型(仅合同模板)
            is_active: 是否启用

        Returns:
            创建的 DocumentTemplate 实例

        Raises:
            ValidationException: 验证失败

        Requirements: 2.1, 2.2, 2.3, 2.5
        """
        template = self.workflow.create_template(
            name=name,
            template_type=template_type,
            contract_sub_type=contract_sub_type,
            file=file,
            file_path=file_path,
            description=description,
            case_types=case_types or [],
            case_stages=case_stages or [],
            contract_types=contract_types or [],
            is_active=is_active,
        )
        logger.info("创建文书模板: %s (ID: %s)", template.name, cast(int, template.pk))
        return template

    def update_template(
        self,
        template_id: int,
        name: str | None = None,
        template_type: str | None = None,
        contract_sub_type: str | None = None,
        file: UploadedFile | None = None,
        file_path: str | None = None,
        description: str | None = None,
        case_types: list[str] | None = None,
        case_stages: list[str] | None = None,
        contract_types: list[str] | None = None,
        is_active: bool | None = None,
        created_by: Any | None = None,
    ) -> DocumentTemplate:
        """
        更新文书模板

        如果更新了文件(file 或 file_path),会自动创建版本记录.

        Args:
            template_id: 模板 ID
            name: 新名称
            template_type: 新模板类型
            contract_sub_type: 新合同子类型
            file: 新上传文件
            file_path: 新文件路径
            description: 新描述
            case_types: 新适用案件类型
            case_stages: 新适用案件阶段
            contract_types: 新适用合同类型
            is_active: 新启用状态
            created_by: 版本创建人(Lawyer 实例)

        Returns:
            更新后的 DocumentTemplate 实例

        Raises:
            NotFoundError: 模板不存在
            ValidationException: 验证失败

        Requirements: 2.6, 2.7
        """
        try:
            template = self.repo.get_by_id(template_id)
        except DocumentTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("文书模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None
        template = self.workflow.update_template(
            template,
            name=name,
            template_type=template_type,
            contract_sub_type=contract_sub_type,
            file=file,
            file_path=file_path,
            description=description,
            case_types=case_types,
            case_stages=case_stages,
            contract_types=contract_types,
            is_active=is_active,
            created_by=created_by,
        )
        logger.info("更新文书模板: %s (ID: %s)", template.name, cast(int, template.pk))
        return template

    def validate_file_path(self, file_path: str) -> Any:
        """
        验证文件路径是否存在

        Args:
            file_path: 文件路径

        Returns:
            文件是否存在

        Requirements: 2.5
        """
        if not file_path:
            return False
        return self.validator.validate_file_path(file_path)

    def get_full_file_path(self, template: DocumentTemplate) -> str | None:
        """
        获取模板文件的完整路径

        Args:
            template: 文书模板实例

        Returns:
            完整文件路径,如果文件不存在返回 None
        """
        try:
            file_path = template.get_file_location()
            if file_path and Path(file_path).exists():
                logger.debug("模板 %s (ID: %s) 文件路径: %s", template.name, cast(int, template.pk), file_path)
                return file_path
            else:
                logger.warning("模板 %s (ID: %s) 文件不存在: %s", template.name, cast(int, template.pk), file_path)
                return None
        except Exception:
            logger.exception(
                "get_full_file_path_failed",
                extra={"template_id": cast(int, template.pk), "template_name": template.name},
            )
            raise

    def extract_placeholders(self, template: DocumentTemplate) -> list[str]:
        """
        从 docx 模板中提取所有占位符

        使用 docxtpl 解析模板,提取所有 {{ xxx }} 格式的占位符.

        Args:
            template: 文书模板实例

        Returns:
            占位符键列表

        Requirements: 2.9, 2.10
        """
        file_path = self.get_full_file_path(template)
        if not file_path:
            logger.warning("模板文件不存在: %s (ID: %s)", template.name, cast(int, template.pk))
            return []
        try:
            result = extract_placeholders_from_file(file_path)
            logger.info("模板 %s (ID: %s) 提取到 %s 个占位符: %s", template.name, cast(int, template.pk), len(result), result)
            return result
        except Exception:
            logger.exception(
                "extract_placeholders_failed",
                extra={"template_id": cast(int, template.pk), "template_name": template.name, "file_path": file_path},
            )
            raise

    def get_undefined_placeholders(self, template: DocumentTemplate) -> list[str]:
        """
        获取模板中未定义的占位符

        对比模板中的占位符和系统已注册的占位符,返回未定义的.

        Args:
            template: 文书模板实例

        Returns:
            未定义的占位符键列表

        Requirements: 2.10
        """
        template_placeholders = set(self.extract_placeholders(template))
        if not template_placeholders:
            return []
        registered_keys = set(Placeholder.objects.filter(is_active=True).values_list("key", flat=True))
        undefined = template_placeholders - registered_keys
        return sorted(list(undefined))

    def get_template_by_id(self, template_id: int) -> DocumentTemplate:
        """
        根据 ID 获取模板

        Args:
            template_id: 模板 ID

        Returns:
            DocumentTemplate 实例

        Raises:
            NotFoundError: 模板不存在
        """
        try:
            return self.repo.get_by_id(template_id)
        except DocumentTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("文书模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None

    def list_templates(
        self, template_type: str | None = None, case_type: str | None = None, is_active: bool | None = None
    ) -> list[DocumentTemplate]:
        """
        列出文书模板

        Args:
            template_type: 按模板类型过滤 (contract/case)
            case_type: 按适用案件类型过滤
            is_active: 按启用状态过滤

        Returns:
            DocumentTemplate 列表
        """
        queryset = self.repo.all()
        if template_type is not None:
            queryset = queryset.filter(template_type=template_type)
        if case_type is not None:
            queryset = queryset.filter(case_types__contains=[case_type])
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset)

    def delete_template(self, template_id: int) -> bool:
        """
        删除模板(软删除)

        Args:
            template_id: 模板 ID

        Returns:
            是否成功

        Raises:
            NotFoundError: 模板不存在
        """
        try:
            template = self.repo.get_by_id(template_id)
        except DocumentTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("文书模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None
        template.is_active = False
        template.save(update_fields=["is_active", "updated_at"])
        logger.info("软删除文书模板: %s (ID: %s)", template.name, cast(int, template.pk))
        return True

    def create_template_from_dict(self, data: dict[str, Any]) -> DocumentTemplate:
        """
        从字典数据创建文书模板

        用于 API 层调用,接收 Schema 转换后的字典数据.

        Args:
            data: 包含模板字段的字典

        Returns:
            创建的 DocumentTemplate 实例

        Raises:
            ValidationException: 验证失败

        Requirements: 1.1
        """
        template = self.workflow.create_from_dict(data)
        logger.info("创建文书模板: %s (ID: %s)", template.name, cast(int, template.pk))
        return template

    def update_template_from_dict(self, template_id: int, data: dict[str, Any]) -> DocumentTemplate:
        """
        从字典数据更新文书模板

        用于 API 层调用,接收 Schema 转换后的字典数据.

        Args:
            template_id: 模板 ID
            data: 包含更新字段的字典

        Returns:
            更新后的 DocumentTemplate 实例

        Raises:
            NotFoundError: 模板不存在
            ValidationException: 验证失败

        Requirements: 1.1
        """
        try:
            template = self.repo.get_by_id(template_id)
        except DocumentTemplate.DoesNotExist:
            raise NotFoundError(
                message=_("文书模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            ) from None
        template = self.workflow.update_from_dict(template, data)
        logger.info("更新文书模板: %s (ID: %s)", template.name, cast(int, template.pk))
        return template
