"""
外部模板填充服务

负责占位符取值、填充预览、自定义字段获取。
单次填充和批量填充方法将在后续任务 (7.2, 7.3) 中实现。

Requirements: 16.1, 16.2, 17.1, 17.2, 17.3
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from django.conf import settings
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FillPreviewItem:
    """填充预览项"""

    position_description: str
    semantic_label: str
    fill_value: str
    value_source: str  # "auto" | "manual" | "empty"
    fill_type: str
    mapping_id: int


@dataclass(frozen=True)
class FillReport:
    """填充报告"""

    total_fields: int
    filled_count: int
    skipped_count: int
    manual_needed: list[str]
    errors: list[str]


class FillingService:
    """模板填充服务：占位符取值 + 填充预览 + 自定义字段"""

    def __init__(self, placeholder_registry: PlaceholderRegistry) -> None:
        self._placeholder_registry = placeholder_registry

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------

    def generate_preview(
        self,
        template_id: int,
        case_id: int,
        party_id: int | None = None,
        custom_values: dict[str, str] | None = None,
    ) -> list[FillPreviewItem]:
        """
        生成填充预览：
        1. 获取模板的所有 FieldMapping（按 sort_order 排序）
        2. 从占位符体系获取案件数据（含当事人数据）
        3. 合并自定义值
        4. 返回每个字段的预览信息（位置、语义、值、来源）
        """
        from apps.documents.models.external_template import (
            ExternalTemplateFieldMapping,
        )

        mappings = ExternalTemplateFieldMapping.objects.filter(
            template_id=template_id,
        ).order_by("sort_order", "id")

        placeholder_values: dict[str, str] = self._get_placeholder_values(
            case_id, party_id
        )
        merged_custom: dict[str, str] = custom_values or {}

        preview_items: list[FillPreviewItem] = []
        for mapping in mappings:
            fill_value: str = ""
            value_source: str = "empty"

            if mapping.placeholder_key and mapping.placeholder_key in placeholder_values:
                fill_value = str(placeholder_values[mapping.placeholder_key])
                value_source = "auto"
            elif not mapping.placeholder_key and mapping.semantic_label in merged_custom:
                fill_value = merged_custom[mapping.semantic_label]
                value_source = "manual"

            preview_items.append(
                FillPreviewItem(
                    position_description=mapping.position_description,
                    semantic_label=mapping.semantic_label,
                    fill_value=fill_value,
                    value_source=value_source,
                    fill_type=mapping.fill_type,
                    mapping_id=mapping.id,
                )
            )

        logger.info(
            "填充预览生成: template_id=%d, case_id=%d, items=%d",
            template_id,
            case_id,
            len(preview_items),
        )
        return preview_items

    def get_custom_fields(self, template_id: int) -> list[dict[str, Any]]:
        """获取需要手动输入的自定义字段列表（placeholder_key 为空的映射）"""
        from apps.documents.models.external_template import (
            ExternalTemplateFieldMapping,
        )

        mappings = ExternalTemplateFieldMapping.objects.filter(
            template_id=template_id,
            placeholder_key="",
        ).order_by("sort_order", "id")

        fields: list[dict[str, Any]] = []
        for mapping in mappings:
            fields.append({
                "mapping_id": mapping.id,
                "semantic_label": mapping.semantic_label,
                "fill_type": mapping.fill_type,
                "options": mapping.options,
                "position_description": mapping.position_description,
            })

        logger.info(
            "自定义字段获取: template_id=%d, count=%d",
            template_id,
            len(fields),
        )
        return fields

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _get_placeholder_values(
        self, case_id: int, party_id: int | None = None
    ) -> dict[str, str]:
        """
        从占位符体系获取案件+当事人的所有占位符值。

        1. 构建 context_data（case_id, party_id）
        2. 遍历 registry 中所有服务，调用 generate(context_data)
        3. 合并所有结果为 dict[str, str]
        """
        context_data: dict[str, Any] = {"case_id": case_id}
        if party_id is not None:
            context_data["party_id"] = party_id

        all_values: dict[str, str] = {}
        services = self._placeholder_registry.get_all_services()

        for service in services:
            try:
                result: dict[str, Any] = service.generate(context_data)
                for key, value in result.items():
                    all_values[key] = str(value) if value is not None else ""
            except Exception:
                logger.exception(
                    "占位符服务 %s 生成失败: case_id=%d",
                    service.name,
                    case_id,
                )

        logger.info(
            "占位符值获取: case_id=%d, party_id=%s, keys=%d",
            case_id,
            party_id,
            len(all_values),
        )
        return all_values
