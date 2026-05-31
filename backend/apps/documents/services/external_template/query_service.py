"""外部模板查询服务。"""

from __future__ import annotations

from typing import Any

from apps.documents.models.external_template import ExternalTemplate, ExternalTemplateFieldMapping

def get_template_or_raise(template_id: int) -> ExternalTemplate:
    """获取外部模板，不存在抛出异常。"""
    return ExternalTemplate.objects.get(pk=template_id)

def get_mappings_by_template(template_id: int) -> Any:
    """获取模板的所有字段映射，按 sort_order 排序。"""
    return ExternalTemplateFieldMapping.objects.filter(template_id=template_id).order_by("sort_order", "id")

def get_mapping_or_raise(mapping_id: int) -> ExternalTemplateFieldMapping:
    """获取字段映射，不存在抛出异常。"""
    return ExternalTemplateFieldMapping.objects.get(pk=mapping_id)
