"""
Documents 模块 Schemas

定义文书生成系统的 API 输入输出数据结构.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from .models import DocumentTemplate, DocumentTemplateType, FolderTemplate, FolderTemplateType, Placeholder

# ============================================================
# 文件夹模板 Schemas
# ============================================================


class FolderTemplateIn(Schema):
    """文件夹模板创建输入"""

    name: str
    template_type: str = FolderTemplateType.CONTRACT
    case_types: list[str] = []
    case_stages: list[str] = []
    contract_types: list[str] = []
    structure: dict[str, Any] = {}
    is_default: bool = False
    is_active: bool = True


class FolderTemplateUpdate(Schema):
    """文件夹模板更新输入"""

    name: str | None = None
    template_type: str | None = None
    case_types: list[str] | None = None
    case_stages: list[str] | None = None
    contract_types: list[str] | None = None
    structure: dict[str, Any] | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class FolderTemplateOut(ModelSchema):
    """文件夹模板输出"""

    template_type_display: str
    case_types_display: str
    case_stages_display: str
    contract_types_display: str

    class Meta:
        model = FolderTemplate
        fields: ClassVar = [
            "id",
            "name",
            "template_type",
            "case_types",
            "case_stages",
            "contract_types",
            "structure",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_template_type_display(obj: FolderTemplate) -> str:
        return str(obj.template_type_display)

    @staticmethod
    def resolve_case_types_display(obj: FolderTemplate) -> str:
        return str(obj.case_types_display)

    @staticmethod
    def resolve_case_stages_display(obj: FolderTemplate) -> str:
        return str(obj.case_stages_display)

    @staticmethod
    def resolve_contract_types_display(obj: FolderTemplate) -> str:
        return str(obj.contract_types_display)


# ============================================================
# 文书模板 Schemas
# ============================================================


class DocumentTemplateIn(Schema):
    """文书模板创建输入"""

    name: str
    template_type: str = DocumentTemplateType.CONTRACT
    file_path: str | None = None
    case_types: list[str] = []
    case_stages: list[str] = []
    contract_types: list[str] = []
    is_active: bool = True


class DocumentTemplateUpdate(Schema):
    """文书模板更新输入"""

    name: str | None = None
    template_type: str | None = None
    file_path: str | None = None
    case_types: list[str] | None = None
    case_stages: list[str] | None = None
    contract_types: list[str] | None = None
    is_active: bool | None = None


class FolderBindingOut(Schema):
    """文件夹绑定输出"""

    id: int
    folder_template_id: int
    folder_template_name: str
    folder_node_id: str
    folder_node_path: str
    is_active: bool


class DocumentTemplateOut(ModelSchema):
    """文书模板输出"""

    template_type_display: str
    case_types_display: str
    case_stages_display: str
    contract_types_display: str
    file_location: str | None = None
    folder_bindings: list[FolderBindingOut] = []

    class Meta:
        model = DocumentTemplate
        fields: ClassVar = [
            "id",
            "name",
            "template_type",
            "file_path",
            "case_types",
            "case_stages",
            "contract_types",
            "is_active",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_template_type_display(obj: DocumentTemplate) -> str:
        return str(obj.template_type_display)

    @staticmethod
    def resolve_case_types_display(obj: DocumentTemplate) -> str:
        return str(obj.case_types_display)

    @staticmethod
    def resolve_case_stages_display(obj: DocumentTemplate) -> str:
        return str(obj.case_stages_display)

    @staticmethod
    def resolve_contract_types_display(obj: DocumentTemplate) -> str:
        return str(obj.contract_types_display)

    @staticmethod
    def resolve_file_location(obj: DocumentTemplate) -> str | None:
        return obj.get_file_location() or None

    @staticmethod
    def resolve_folder_bindings(obj: DocumentTemplate) -> list[FolderBindingOut]:
        return [
            FolderBindingOut(
                id=binding.id,
                folder_template_id=binding.folder_template_id,
                folder_template_name=binding.folder_template.name,
                folder_node_id=binding.folder_node_id,
                folder_node_path=binding.folder_node_path,
                is_active=binding.is_active,
            )
            for binding in obj.folder_bindings.all()
        ]


# ============================================================
# 替换词 Schemas
# ============================================================


class PlaceholderIn(Schema):
    """替换词创建输入"""

    key: str
    display_name: str
    example_value: str = ""
    description: str = ""
    is_active: bool = True


class PlaceholderUpdate(Schema):
    """替换词更新输入"""

    key: str | None = None
    display_name: str | None = None
    example_value: str | None = None
    description: str | None = None
    is_active: bool | None = None


class PlaceholderOut(ModelSchema):
    """替换词输出"""

    class Meta:
        model = Placeholder
        fields: ClassVar = [
            "id",
            "key",
            "display_name",
            "example_value",
            "description",
            "is_active",
        ]


class PlaceholderPreviewOut(Schema):
    contract_id: int
    values: dict[str, Any]
    missing_keys: list[str] = []


# ============================================================
# 枚举选项 Schemas
# ============================================================


class EnumOptionOut(Schema):
    """枚举选项输出"""

    value: str
    label: str


class DocumentEnumsOut(Schema):
    """文书系统枚举选项输出"""

    case_types: list[EnumOptionOut]
    case_stages: list[EnumOptionOut]
    contract_types: list[EnumOptionOut]
    template_types: list[EnumOptionOut]
    folder_template_types: list[EnumOptionOut]
