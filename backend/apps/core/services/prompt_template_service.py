"""
Prompt 模板服务

提供 Prompt 模板的 CRUD 操作和缓存管理.
"""

from django.utils.translation import gettext_lazy as _
from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.infrastructure import CacheKeys, delete_cache_key
from apps.core.models.prompt_template import PromptTemplate
from apps.core.repositories.prompt_template_repository import PromptTemplateRepository


class PromptTemplateService:
    """Prompt 模板服务"""

    def __init__(self, *, repository: PromptTemplateRepository | None = None) -> None:
        self._repository = repository or PromptTemplateRepository()

    @transaction.atomic
    def create_template(
        self,
        name: str,
        title: str,
        template: str,
        description: str = "",
        variables: list[str] | None = None,
        category: str = "general",
        is_active: bool = True,
        version: str = "1.0",
    ) -> PromptTemplate:
        """
        创建 Prompt 模板

        Args:
            name: 模板名称(唯一标识)
            title: 显示标题
            template: 模板内容
            description: 模板描述
            variables: 变量列表
            category: 分类
            is_active: 是否启用
            version: 版本

        Returns:
            创建的 PromptTemplate 实例
        """
        if not name or not name.strip():
            raise ValidationException(
                message=_("模板名称不能为空"),
                code="INVALID_TEMPLATE_NAME",
                errors={"name": "模板名称不能为空"},
            )

        if not title or not title.strip():
            raise ValidationException(
                message=_("显示标题不能为空"),
                code="INVALID_TEMPLATE_TITLE",
                errors={"title": "显示标题不能为空"},
            )

        prompt_template = self._repository.create(
            name=name.strip(),
            title=title.strip(),
            template=template,
            description=description,
            category=category,
            is_active=is_active,
            version=version,
        )

        # 清除缓存
        self._clear_cache(name)

        return prompt_template

    @transaction.atomic
    def update_template(
        self,
        template_id: int,
        title: str | None = None,
        template: str | None = None,
        description: str | None = None,
        variables: list[str] | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        version: str | None = None,
    ) -> PromptTemplate:
        """
        更新 Prompt 模板

        Args:
            template_id: 模板 ID
            title: 新标题
            template: 新模板内容
            description: 新描述
            variables: 新变量列表
            category: 新分类
            is_active: 新启用状态
            version: 新版本

        Returns:
            更新后的 PromptTemplate 实例
        """
        prompt_template = self._repository.get_by_id(template_id)
        if prompt_template is None:
            raise NotFoundError(
                message=_("Prompt 模板不存在"),
                code="PROMPT_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )

        if title is not None:
            if not title or not title.strip():
                raise ValidationException(
                    message=_("显示标题不能为空"),
                    code="INVALID_TEMPLATE_TITLE",
                    errors={"title": "显示标题不能为空"},
                )
            prompt_template.title = title.strip()

        if template is not None:
            prompt_template.template = template

        if description is not None:
            prompt_template.description = description

        if variables is not None:
            prompt_template.variables = variables

        if category is not None:
            prompt_template.category = category

        if is_active is not None:
            prompt_template.is_active = is_active

        if version is not None:
            prompt_template.version = version

        prompt_template.save()

        # 清除缓存
        self._clear_cache(prompt_template.name)

        return prompt_template

    @transaction.atomic
    def delete_template(self, template_id: int) -> bool:
        """
        删除 Prompt 模板

        Args:
            template_id: 模板 ID

        Returns:
            是否成功
        """
        prompt_template = self._repository.get_by_id(template_id)
        if prompt_template is None:
            raise NotFoundError(
                message=_("Prompt 模板不存在"),
                code="PROMPT_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )

        name = prompt_template.name
        prompt_template.delete()

        # 清除缓存
        self._clear_cache(name)

        return True

    def get_template(self, template_id: int) -> PromptTemplate:
        """
        获取 Prompt 模板

        Args:
            template_id: 模板 ID

        Returns:
            PromptTemplate 实例
        """
        prompt_template = self._repository.get_by_id(template_id)
        if prompt_template is None:
            raise NotFoundError(
                message=_("Prompt 模板不存在"),
                code="PROMPT_TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )
        return prompt_template

    def get_template_by_name(self, name: str) -> PromptTemplate | None:
        """
        根据名称获取 Prompt 模板

        Args:
            name: 模板名称

        Returns:
            PromptTemplate 实例,不存在时返回 None
        """
        return self._repository.get_by_name(name)

    def list_templates(
        self,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> list[PromptTemplate]:
        """
        列出 Prompt 模板

        Args:
            category: 按分类过滤
            is_active: 按启用状态过滤

        Returns:
            PromptTemplate 列表
        """
        templates = self._repository.get_all_active()

        if category is not None:
            templates = [t for t in templates if t.category == category]

        if is_active is not None:
            templates = [t for t in templates if t.is_active == is_active]

        return sorted(templates, key=lambda t: (t.category, t.name))

    def _clear_cache(self, name: str) -> None:
        """清除 Prompt 模板缓存"""
        delete_cache_key(CacheKeys.prompt_template(name))
