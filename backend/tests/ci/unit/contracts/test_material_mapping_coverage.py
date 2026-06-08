"""测试归档材料映射逻辑

覆盖: apps/contracts/services/archive/checklist/material_mapping.py
重点: match_type_name_to_code, 纯逻辑函数
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.checklist.material_mapping import (
    match_type_name_to_code,
)


# ============================================================
# match_type_name_to_code
# ============================================================


class TestMatchTypeNameToCode:
    """测试材料类型名称到清单编号的匹配"""

    def test_exact_keyword_match(self) -> None:
        keyword_map = {"code_1": ["授权委托"], "code_2": ["判决书"]}
        result = match_type_name_to_code("授权委托书", keyword_map)
        assert result == "code_1"

    def test_partial_keyword_match(self) -> None:
        keyword_map = {"code_1": ["授权"], "code_2": ["判决"]}
        result = match_type_name_to_code("公民授权委托书", keyword_map)
        assert result == "code_1"

    def test_no_match(self) -> None:
        keyword_map = {"code_1": ["授权"], "code_2": ["判决"]}
        result = match_type_name_to_code("合同文本", keyword_map)
        assert result is None

    def test_empty_type_name(self) -> None:
        keyword_map = {"code_1": ["授权"]}
        result = match_type_name_to_code("", keyword_map)
        assert result is None

    def test_empty_keyword_map(self) -> None:
        result = match_type_name_to_code("授权委托书", {})
        assert result is None

    def test_multiple_keywords_first_match_wins(self) -> None:
        """第一个匹配到的 code 返回"""
        keyword_map = {"code_a": ["授权"], "code_b": ["委托"]}
        result = match_type_name_to_code("授权委托书", keyword_map)
        assert result == "code_a"

    def test_first_code_wins_when_multiple_codes_match(self) -> None:
        keyword_map = {"code_1": ["授权", "委托"], "code_2": ["委托书"]}
        result = match_type_name_to_code("授权委托书", keyword_map)
        assert result == "code_1"

    def test_none_type_name(self) -> None:
        keyword_map = {"code_1": ["授权"]}
        result = match_type_name_to_code(None, keyword_map)  # type: ignore[arg-type]
        assert result is None


# ============================================================
# map_contract_materials (via mocking)
# ============================================================


class TestMapContractMaterials:
    """测试合同材料映射"""

    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_source")
    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_name")
    def test_contract_original_mapped(
        self, mock_find_name: MagicMock, mock_find_source: MagicMock
    ) -> None:
        from apps.contracts.models.finalized_material import MaterialCategory
        from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials

        mock_find_source.return_value = "lt_5"
        mock_find_name.return_value = "lt_7"

        material = MagicMock()
        material.id = 1
        material.archive_item_code = ""
        material.category = MaterialCategory.CONTRACT_ORIGINAL

        result = map_contract_materials("litigation", [material])
        assert "lt_5" in result
        assert 1 in result["lt_5"]

    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_source")
    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_name")
    def test_invoice_mapped(
        self, mock_find_name: MagicMock, mock_find_source: MagicMock
    ) -> None:
        from apps.contracts.models.finalized_material import MaterialCategory
        from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials

        mock_find_source.return_value = "lt_5"
        mock_find_name.return_value = "lt_7"

        material = MagicMock()
        material.id = 2
        material.archive_item_code = ""
        material.category = MaterialCategory.INVOICE

        result = map_contract_materials("litigation", [material])
        assert "lt_7" in result
        assert 2 in result["lt_7"]

    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_source")
    @patch("apps.contracts.services.archive.checklist.checklist_query.find_code_by_name")
    def test_material_with_existing_code_skipped(
        self, mock_find_name: MagicMock, mock_find_source: MagicMock
    ) -> None:
        from apps.contracts.models.finalized_material import MaterialCategory
        from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials

        mock_find_source.return_value = "lt_5"
        mock_find_name.return_value = "lt_7"

        material = MagicMock()
        material.id = 3
        material.archive_item_code = "lt_5"  # Already assigned
        material.category = MaterialCategory.CONTRACT_ORIGINAL

        result = map_contract_materials("litigation", [material])
        assert result == {}


# ============================================================
# map_supervision_card_materials
# ============================================================


class TestMapSupervisionCardMaterials:
    """测试监督卡材料映射"""

    @patch("apps.contracts.services.archive.checklist.material_mapping.ARCHIVE_CHECKLIST")
    def test_maps_supervision_card(self, mock_checklist: dict) -> None:
        from apps.contracts.models.finalized_material import MaterialCategory
        from apps.contracts.services.archive.checklist.material_mapping import map_supervision_card_materials

        mock_checklist.get.return_value = [
            {"code": "lt_10", "auto_detect": "supervision_card", "name": "监督卡"}
        ]

        material = MagicMock()
        material.id = 5
        material.archive_item_code = ""
        material.category = MaterialCategory.SUPERVISION_CARD

        result = map_supervision_card_materials("litigation", [material])
        assert "lt_10" in result
        assert 5 in result["lt_10"]

    @patch("apps.contracts.services.archive.checklist.material_mapping.ARCHIVE_CHECKLIST")
    def test_no_supervision_code_returns_empty(self, mock_checklist: dict) -> None:
        from apps.contracts.models.finalized_material import MaterialCategory
        from apps.contracts.services.archive.checklist.material_mapping import map_supervision_card_materials

        mock_checklist.get.return_value = [
            {"code": "lt_1", "auto_detect": None, "name": "封面"}
        ]

        material = MagicMock()
        material.id = 5
        material.archive_item_code = ""
        material.category = MaterialCategory.SUPERVISION_CARD

        result = map_supervision_card_materials("litigation", [material])
        assert result == {}
