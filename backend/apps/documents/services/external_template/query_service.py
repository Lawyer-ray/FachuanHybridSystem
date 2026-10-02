"""外部模板查询服务。"""

from __future__ import annotations

from typing import Any

from apps.documents.models.external_template import ExternalTemplate, ExternalTemplateFieldMapping


def get_template_or_raise(template_id: int, law_firm_id: int | None = None) -> ExternalTemplate:  # pragma: no cover
    """获取外部模板，不存在抛出异常。

    传入 law_firm_id 时按律所过滤（安全审计 B-05：跨律所模板隔离；
    传 None（如 superuser）不过滤）。
    """
    qs = ExternalTemplate.objects.all()
    if law_firm_id is not None:
        qs = qs.filter(law_firm_id=law_firm_id)
    return qs.get(pk=template_id)


def get_mappings_by_template(template_id: int) -> Any:  # pragma: no cover
    """获取模板的所有字段映射，按 sort_order 排序。"""
    return ExternalTemplateFieldMapping.objects.filter(template_id=template_id).order_by("sort_order", "id")


def get_mapping_or_raise(mapping_id: int) -> ExternalTemplateFieldMapping:  # pragma: no cover
    """获取字段映射，不存在抛出异常。"""
    return ExternalTemplateFieldMapping.objects.get(pk=mapping_id)
