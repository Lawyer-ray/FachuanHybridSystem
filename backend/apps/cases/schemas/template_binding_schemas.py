"""案件模板绑定相关 Schema."""

from __future__ import annotations

from ninja import Schema


class BindTemplateRequestSchema(Schema):
    """绑定模板请求"""

    template_id: int


class GenerateTemplateRequestSchema(Schema):
    """生成模板请求"""

    template_id: int
    client_id: int | None = None  # 单个当事人ID(法定代表人身份证明书、单独授权)
    client_ids: list[int] | None = None  # 多个当事人ID(合并授权)
    mode: str | None = None  # 授权模式: 'individual' | 'combined'


class TemplateBindingSchema(Schema):
    """模板绑定信息"""

    binding_id: int | None = None  # 通用模板无绑定记录,binding_id 为 None
    template_id: int
    name: str
    description: str = ""
    binding_source: str
    binding_source_display: str
    created_at: str | None = None


class TemplateCategorySchema(Schema):
    """模板分类"""

    category: str
    category_display: str
    templates: list[TemplateBindingSchema]


class BindingsResponseSchema(Schema):
    """绑定列表响应"""

    categories: list[TemplateCategorySchema]
    total_count: int


class AvailableTemplateSchema(Schema):
    """可用模板信息"""

    template_id: int
    name: str
    description: str = ""
    case_sub_type: str | None = None
    case_sub_type_display: str = ""


class SuccessResponseSchema(Schema):
    """成功响应"""

    success: bool = True
