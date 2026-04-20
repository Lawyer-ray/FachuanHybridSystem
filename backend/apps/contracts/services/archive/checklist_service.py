"""归档检查清单服务

负责计算归档完成度、获取检查清单状态等业务逻辑。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial

from .category_mapping import ArchiveCategory, get_archive_category
from .constants import ARCHIVE_CHECKLIST, ChecklistItem

logger = logging.getLogger("apps.contracts.archive")


class ArchiveChecklistService:
    """归档检查清单服务"""

    def get_checklist_with_status(self, contract: Contract) -> dict[str, Any]:
        """
        获取合同的归档检查清单及各项完成状态。

        Args:
            contract: 合同实例

        Returns:
            {
                "archive_category": "litigation",
                "archive_category_label": "诉讼/仲裁",
                "items": [
                    {
                        "code": "lt_1",
                        "name": "案卷封面",
                        "template": "case_cover",
                        "required": True,
                        "auto_detect": None,
                        "source": "template",
                        "completed": True,
                        "material_ids": [1, 2],  # 关联的 FinalizedMaterial ID 列表
                    },
                    ...
                ],
                "completed_count": 8,
                "total_count": 18,
                "required_completed_count": 5,
                "required_total_count": 8,
                "completion_percentage": 44.4,
            }
        """
        archive_category = get_archive_category(contract.case_type)
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

        # 一次性加载合同的所有归档材料
        materials = list(
            FinalizedMaterial.objects.filter(contract=contract).only(
                "id", "archive_item_code", "category"
            )
        )

        # 构建 archive_item_code → [material_id] 映射
        code_to_materials: dict[str, list[int]] = {}
        for m in materials:
            if m.archive_item_code:
                code_to_materials.setdefault(m.archive_item_code, []).append(m.id)

        # 特殊处理：合同正本/补充协议/发票归类到对应检查项
        contract_category_codes = self._map_contract_materials(
            archive_category, materials
        )
        for code, mat_ids in contract_category_codes.items():
            code_to_materials.setdefault(code, []).extend(mat_ids)

        # 构建结果
        items_with_status: list[dict[str, Any]] = []
        for item in checklist_items:
            mat_ids = code_to_materials.get(item["code"], [])
            items_with_status.append({
                **item,
                "completed": len(mat_ids) > 0,
                "material_ids": mat_ids,
            })

        total_count = len(items_with_status)
        completed_count = sum(1 for item in items_with_status if item["completed"])
        required_items = [item for item in items_with_status if item["required"]]
        required_total_count = len(required_items)
        required_completed_count = sum(1 for item in required_items if item["completed"])

        archive_category_label = ArchiveCategory(archive_category).label

        return {
            "archive_category": archive_category,
            "archive_category_label": archive_category_label,
            "items": items_with_status,
            "completed_count": completed_count,
            "total_count": total_count,
            "required_completed_count": required_completed_count,
            "required_total_count": required_total_count,
            "completion_percentage": round(completed_count / total_count * 100, 1) if total_count > 0 else 0,
        }

    def _map_contract_materials(
        self,
        archive_category: str,
        materials: list[FinalizedMaterial],
    ) -> dict[str, list[int]]:
        """
        将现有 MaterialCategory (合同正本/补充协议/发票) 映射到检查清单编号。

        这是为了兼容已上传的归档材料，让它们自动匹配到检查清单项。
        """
        result: dict[str, list[int]] = {}

        # 找到"委托合同"对应的 code
        contract_code = self._find_code_by_source(archive_category, "contract")
        invoice_code = self._find_code_by_name(archive_category, "收费凭证")

        for m in materials:
            # 已有 archive_item_code 的跳过
            if m.archive_item_code:
                continue

            from apps.contracts.models.finalized_material import MaterialCategory

            if m.category in (MaterialCategory.CONTRACT_ORIGINAL, MaterialCategory.SUPPLEMENTARY_AGREEMENT) and contract_code:
                result.setdefault(contract_code, []).append(m.id)
            elif m.category == MaterialCategory.INVOICE and invoice_code:
                result.setdefault(invoice_code, []).append(m.id)

        return result

    def _find_code_by_source(self, archive_category: str, source: str) -> str | None:
        """根据 source 类型找到对应的检查清单 code

        名称匹配说明：
        - 非诉: "委托合同（客户授权证明材料等）" → 包含"委托"
        - 诉讼: "委托合同、风险告知书、授权委托证明材料等" → 包含"委托"
        - 刑事: "委托代理合同、风险告知书、授权委托证明材料等" → 包含"委托"
        统一使用"委托"关键词匹配，兼容所有分类。
        """
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist_items:
            if item["source"] == source and "委托" in item["name"]:
                return item["code"]
        return None

    def _find_code_by_name(self, archive_category: str, name_keyword: str) -> str | None:
        """根据名称关键词找到对应的检查清单 code"""
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist_items:
            if name_keyword in item["name"]:
                return item["code"]
        return None

    def get_template_items(self, archive_category: str) -> list[ChecklistItem]:
        """获取指定归档分类中需要模板生成的清单项"""
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        return [item for item in checklist_items if item["template"] is not None]

    def get_auto_detect_items(self, archive_category: str) -> list[ChecklistItem]:
        """获取指定归档分类中支持自动检测的清单项"""
        checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])
        return [item for item in checklist_items if item["auto_detect"] is not None]
