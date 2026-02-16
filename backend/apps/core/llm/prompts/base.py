"""Module for base."""

from __future__ import annotations

"""
Prompt 基类和管理器模块

定义 PromptTemplate 数据类和 PromptManager 管理器.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from dataclasses import dataclass, field
from typing import ClassVar

from apps.core.exceptions import NotFoundError, ValidationException


@dataclass
class CodePromptTemplate:
    """
    代码中的 Prompt 模板数据类

    Attributes:
        name: 模板名称(唯一标识)
        template: 模板内容(支持 {variable_name} 语法)
        description: 模板描述
        variables: 必需变量列表
    """

    name: str
    template: str
    description: str = ""
    variables: list[str] = field(default_factory=list)


class PromptManager:
    """
    Prompt 模板管理器

    提供模板的注册、获取、渲染功能.

    Example:
        # 注册模板
        template = CodePromptTemplate(
            name="greeting",
            template="你好,{name}!欢迎来到 {place}.",
            description="问候语模板",
            variables=["name", "place"]
        )
        PromptManager.register(template)

        # 渲染模板
        result = PromptManager.render("greeting", name="张三", place="北京")
        # 输出: "你好,张三!欢迎来到北京."
    """

    _templates: ClassVar[dict[str, CodePromptTemplate]] = {}

    @classmethod
    def register(cls, template: CodePromptTemplate) -> None:
        """
        注册 Prompt 模板

        Args:
            template: CodePromptTemplate 实例
        """
        cls._templates[template.name] = template

    @classmethod
    def get(cls, name: str) -> CodePromptTemplate:
        """
        获取 Prompt 模板

        Args:
            name: 模板名称

        Returns:
            CodePromptTemplate 实例

        Raises:
            NotFoundError: 模板不存在
        """
        if name not in cls._templates:
            raise NotFoundError(
                message=f"Prompt 模板 '{name}' 不存在",
                code="PROMPT_NOT_FOUND",
                errors={"name": f"模板 '{name}' 未注册"},
            )
        return cls._templates[name]

    @classmethod
    def render(cls, name: str, **variables) -> str:  # type: ignore[no-untyped-def]
        """
        渲染 Prompt 模板

        Args:
            name: 模板名称
            **variables: 变量值

        Returns:
            渲染后的 Prompt 字符串

        Raises:
            NotFoundError: 模板不存在
            ValidationException: 缺少必需变量
        """
        template = cls.get(name)

        # 检查必需变量是否都已提供
        missing_vars = [var for var in template.variables if var not in variables]
        if missing_vars:
            raise ValidationException(
                message=f"缺少必需变量: {', '.join(missing_vars)}",
                code="PROMPT_MISSING_VARIABLES",
                errors={"missing_variables": missing_vars},
            )

        # 使用 str.format() 进行变量替换
        return template.template.format(**variables)

    @classmethod
    def list_templates(cls) -> list[str]:
        """
        列出所有已注册的模板名称

        Returns:
            模板名称列表
        """
        return list(cls._templates.keys())

    @classmethod
    def clear(cls) -> None:
        """
        清空所有已注册的模板(主要用于测试)
        """
        cls._templates = {}
