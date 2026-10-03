"""外部模板查询服务。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import PermissionDenied
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


def ensure_templates_owned(template_ids: list[int], user: Any) -> None:  # pragma: no cover
    """校验批量模板均属于当前律所（安全审计 B-05，superuser 豁免）。

    与 API 时期口径一致：无律所用户（law_firm_id=None）按律所过滤查询，
    未命中的模板（含全部）作为 foreign 清单抛 ``PermissionDenied``（HTTP 403）。
    """
    if getattr(user, "is_superuser", False):
        return

    firm_id = getattr(user, "law_firm_id", None)
    own_ids = set(
        ExternalTemplate.objects.filter(pk__in=list(template_ids), law_firm_id=firm_id).values_list("pk", flat=True)
    )
    foreign = [tid for tid in template_ids if tid not in own_ids]
    if foreign:
        raise PermissionDenied(
            message="包含无权使用的外部模板", code="TEMPLATE_FIRM_FORBIDDEN", errors={"template_ids": foreign}
        )


def update_mapping_fields(
    mapping: ExternalTemplateFieldMapping,
    *,
    semantic_label: str | None,
    fill_type: str | None,
    position_description: str | None,
) -> None:  # pragma: no cover
    """按非空字段更新字段映射并保存（updated_at 恒参与更新）。"""
    update_fields: list[str] = ["updated_at"]
    if semantic_label is not None:
        mapping.semantic_label = semantic_label
        update_fields.append("semantic_label")
    if fill_type is not None:
        mapping.fill_type = fill_type
        update_fields.append("fill_type")
    if position_description is not None:
        mapping.position_description = position_description
        update_fields.append("position_description")
    mapping.save(update_fields=update_fields)
