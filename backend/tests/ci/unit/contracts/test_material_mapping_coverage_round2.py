"""补充覆盖测试: contracts/services/archive/checklist/material_mapping.py

覆盖: map_contract_materials, map_case_authorization_materials,
map_supervision_card_materials, find_case_material_match_codes,
_search_keyword_map（既有文件已覆盖 match_type_name_to_code /
fill_material_details_from_ids，此处不重复）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models.finalized_material import MaterialCategory
from apps.contracts.services.archive.checklist.material_mapping import (
    _search_keyword_map,
    find_case_material_match_codes,
    map_case_authorization_materials,
    map_contract_materials,
    map_supervision_card_materials,
)


def _mat(mat_id: int, category: str, *, archive_item_code: str = "") -> MagicMock:
    m = MagicMock()
    m.id = mat_id
    m.category = category
    m.archive_item_code = archive_item_code
    return m


# ── map_contract_materials ────────────────────────────────────────


class TestMapContractMaterials:
    def test_contract_original_and_supplementary_mapped(self):
        materials = [
            _mat(1, MaterialCategory.CONTRACT_ORIGINAL),
            _mat(2, MaterialCategory.SUPPLEMENTARY_AGREEMENT),
            _mat(3, MaterialCategory.SUPERVISION_CARD),  # 不属于合同源类别
        ]
        result = map_contract_materials("non_litigation", materials)
        assert len(result) == 1
        code, ids = next(iter(result.items()))
        assert ids == [1, 2]

    def test_invoice_mapped_to_separate_code(self):
        materials = [
            _mat(1, MaterialCategory.INVOICE),
            _mat(2, MaterialCategory.CONTRACT_ORIGINAL),
        ]
        result = map_contract_materials("non_litigation", materials)
        # 发票与合同正本映射到不同清单编号
        assert len(result) == 2
        invoice_code = next(code for code, ids in result.items() if ids == [1])
        contract_code = next(code for code, ids in result.items() if ids == [2])
        assert invoice_code != contract_code

    def test_material_with_archive_item_code_skipped(self):
        materials = [
            _mat(1, MaterialCategory.CONTRACT_ORIGINAL, archive_item_code="nl_4"),
            _mat(2, MaterialCategory.INVOICE, archive_item_code="nl_5"),
        ]
        result = map_contract_materials("non_litigation", materials)
        assert result == {}

    def test_empty_materials(self):
        assert map_contract_materials("non_litigation", []) == {}

    def test_unknown_category_returns_empty(self):
        """未知归档分类找不到合同源/发票清单编号 → 空映射。"""
        materials = [_mat(1, MaterialCategory.CONTRACT_ORIGINAL), _mat(2, MaterialCategory.INVOICE)]
        result = map_contract_materials("unknown_category", materials)
        assert result == {}


# ── map_case_authorization_materials ─────────────────────────────


class TestMapCaseAuthorizationMaterials:
    def test_unknown_category_returns_empty(self):
        contract = MagicMock()
        result = map_case_authorization_materials(
            contract, "unknown_category", [_mat(1, MaterialCategory.AUTHORIZATION_MATERIAL)]
        )
        assert result == {}

    def test_authorization_materials_mapped(self):
        contract = MagicMock()
        contract.id = 1
        materials = [
            _mat(1, MaterialCategory.AUTHORIZATION_MATERIAL),
            _mat(2, MaterialCategory.AUTHORIZATION_MATERIAL, archive_item_code="lt_20"),
            _mat(3, MaterialCategory.CASE_MATERIAL),
        ]
        with patch("apps.cases.models.CaseMaterial") as case_material:
            case_material.objects.filter.return_value.exists.return_value = True
            result = map_case_authorization_materials(contract, "litigation", materials)
        # 仅无归档编号的授权材料映射；关联案件查询走 EXISTS
        assert len(result) == 1
        code, ids = next(iter(result.items()))
        assert ids == [1]
        assert code.startswith("lt_")

    def test_case_material_query_exception_swallowed(self):
        contract = MagicMock()
        contract.id = 1
        materials = [_mat(1, MaterialCategory.AUTHORIZATION_MATERIAL)]
        with patch("apps.cases.models.CaseMaterial") as case_material:
            case_material.objects.filter.side_effect = RuntimeError("db down")
            result = map_case_authorization_materials(contract, "litigation", materials)
        # 查询异常仅告警，不影响映射结果
        assert len(result) == 1

    def test_no_matching_materials(self):
        contract = MagicMock()
        result = map_case_authorization_materials(contract, "litigation", [_mat(9, MaterialCategory.CASE_MATERIAL)])
        assert result == {}


# ── map_supervision_card_materials ────────────────────────────────


class TestMapSupervisionCardMaterials:
    def test_supervision_card_mapped(self):
        """criminal 清单含 auto_detect=supervision_card 项（cr_16）。"""
        materials = [
            _mat(1, MaterialCategory.SUPERVISION_CARD),
            _mat(2, MaterialCategory.SUPERVISION_CARD, archive_item_code="cr_16"),
            _mat(3, MaterialCategory.CONTRACT_ORIGINAL),
        ]
        result = map_supervision_card_materials("criminal", materials)
        assert result == {"cr_16": [1]}

    def test_category_without_supervision_item_returns_empty(self):
        """三大归档分类均含监督卡清单项；未知分类取不到清单 → 空映射。"""
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST

        for category in ARCHIVE_CHECKLIST:
            assert any(item.get("auto_detect") == "supervision_card" for item in ARCHIVE_CHECKLIST[category]), (
                f"{category} 应含监督卡清单项（测试前提）"
            )
        assert map_supervision_card_materials("unknown_category", [_mat(1, MaterialCategory.SUPERVISION_CARD)]) == {}

    def test_empty_materials(self):
        assert map_supervision_card_materials("criminal", []) == {}


# ── find_case_material_match_codes ────────────────────────────────


class TestFindCaseMaterialMatchCodes:
    def test_unknown_category_returns_empty_set(self):
        contract = MagicMock()
        with patch("apps.cases.models.CaseMaterial") as case_material:
            result = find_case_material_match_codes(contract, "unknown_category")
            case_material.objects.filter.assert_not_called()
        assert result == set()

    def test_matched_codes_aggregated(self):
        contract = MagicMock()
        contract.cases.all.return_value = [MagicMock(id=1)]
        with patch("apps.cases.models.CaseMaterial") as case_material:
            case_material.objects.filter.return_value.values_list.return_value = [
                "授权委托书",
                "起诉状",
                "无关材料",
                "",
            ]
            result = find_case_material_match_codes(contract, "litigation")
        # 授权委托书命中 lt_20；起诉状/无关材料不命中授权关键词
        assert "lt_20" in result
        assert all(code.startswith("lt_") for code in result)

    def test_query_exception_returns_empty_set(self):
        contract = MagicMock()
        with patch("apps.cases.models.CaseMaterial") as case_material:
            case_material.objects.filter.side_effect = RuntimeError("join too complex")
            result = find_case_material_match_codes(contract, "litigation")
        assert result == set()


# ── _search_keyword_map ───────────────────────────────────────────


class TestSearchKeywordMap:
    def test_first_match_wins_in_iteration_order(self):
        mapping = {"code_a": ["授权"], "code_b": ["授权委托书"]}
        hit = _search_keyword_map(mapping, "授权委托书")
        assert hit == ("code_a", "授权")

    def test_no_match_returns_none(self):
        assert _search_keyword_map({"code_a": ["授权"]}, "判决书") is None

    def test_empty_mapping(self):
        assert _search_keyword_map({}, "任何") is None

    def test_empty_keyword_list(self):
        assert _search_keyword_map({"code_a": []}, "任何") is None


# ── 交叉回归: map_* 组合被 checklist 消费的结构 ──────────────────


class TestMappingResultShape:
    def test_all_mappings_use_material_id_lists(self) -> None:
        materials: list[Any] = [
            _mat(1, MaterialCategory.CONTRACT_ORIGINAL),
            _mat(2, MaterialCategory.SUPERVISION_CARD),
            _mat(3, MaterialCategory.AUTHORIZATION_MATERIAL),
        ]
        contract = MagicMock()
        contract.id = 1
        with patch("apps.cases.models.CaseMaterial") as case_material:
            case_material.objects.filter.return_value.exists.return_value = False
            contract_map = map_contract_materials("litigation", materials)
            auth_map = map_case_authorization_materials(contract, "litigation", materials)
        supervision_map = map_supervision_card_materials("litigation", materials)
        for mapping in (contract_map, auth_map, supervision_map):
            for code, ids in mapping.items():
                assert isinstance(code, str) and code
                assert all(isinstance(i, int) for i in ids)
        assert contract_map and auth_map  # litigation 下合同与授权都有对应清单项
