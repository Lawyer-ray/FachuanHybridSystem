"""补充覆盖测试: contracts/services/archive/checklist/checklist_query.py + material_mapping.py

覆盖: _apply_subitem_order, _get_source, _get_source_label,
find_code_by_source, find_code_by_name, get_template_items,
get_auto_detect_items, match_type_name_to_code, fill_material_details_from_ids
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models.finalized_material import MaterialCategory
from apps.contracts.services.archive.checklist.checklist_query import (
    _apply_subitem_order,
    _get_source,
    _get_source_label,
    find_code_by_name,
    find_code_by_source,
    get_auto_detect_items,
    get_template_items,
)
from apps.contracts.services.archive.checklist.material_mapping import (
    fill_material_details_from_ids,
    match_type_name_to_code,
)


# ── _get_source ───────────────────────────────────────────────────


class TestGetSource:
    def test_contract_original(self) -> None:
        assert _get_source(MaterialCategory.CONTRACT_ORIGINAL) == "contract"

    def test_supplementary_agreement(self) -> None:
        assert _get_source(MaterialCategory.SUPPLEMENTARY_AGREEMENT) == "contract"

    def test_invoice(self) -> None:
        assert _get_source(MaterialCategory.INVOICE) == "contract"

    def test_archive_document(self) -> None:
        assert _get_source(MaterialCategory.ARCHIVE_DOCUMENT) == "auto"

    def test_supervision_card(self) -> None:
        assert _get_source(MaterialCategory.SUPERVISION_CARD) == "upload"

    def test_authorization_material(self) -> None:
        assert _get_source(MaterialCategory.AUTHORIZATION_MATERIAL) == "case"

    def test_case_material(self) -> None:
        assert _get_source(MaterialCategory.CASE_MATERIAL) == "case"

    def test_archive_upload(self) -> None:
        assert _get_source(MaterialCategory.ARCHIVE_UPLOAD) == "upload"

    def test_unknown_fallback(self) -> None:
        assert _get_source("some_unknown_category") == "upload"


# ── _get_source_label ─────────────────────────────────────────────


class TestGetSourceLabel:
    def test_contract_original(self) -> None:
        assert _get_source_label(MaterialCategory.CONTRACT_ORIGINAL) == "合同正本"

    def test_supplementary_agreement(self) -> None:
        assert _get_source_label(MaterialCategory.SUPPLEMENTARY_AGREEMENT) == "补充协议"

    def test_invoice(self) -> None:
        assert _get_source_label(MaterialCategory.INVOICE) == "发票"

    def test_archive_document(self) -> None:
        assert _get_source_label(MaterialCategory.ARCHIVE_DOCUMENT) == "自动生成"

    def test_supervision_card(self) -> None:
        assert _get_source_label(MaterialCategory.SUPERVISION_CARD) == "监督卡"

    def test_authorization_material(self) -> None:
        assert _get_source_label(MaterialCategory.AUTHORIZATION_MATERIAL) == "授权委托"

    def test_case_material(self) -> None:
        assert _get_source_label(MaterialCategory.CASE_MATERIAL) == "案件同步"

    def test_archive_upload(self) -> None:
        assert _get_source_label(MaterialCategory.ARCHIVE_UPLOAD) == "手动上传"

    def test_unknown_fallback(self) -> None:
        assert _get_source_label("unknown") == "手动上传"


# ── find_code_by_source ───────────────────────────────────────────


class TestFindCodeBySource:
    def test_finds_contract_source_with_委托_in_name(self) -> None:
        # non_litigation has nl_4 with source="contract" and "委托" in name
        result = find_code_by_source("non_litigation", "contract")
        assert result is not None
        assert isinstance(result, str)

    def test_returns_none_for_no_match(self) -> None:
        result = find_code_by_source("non_litigation", "nonexistent_source")
        assert result is None

    def test_returns_none_for_unknown_category(self) -> None:
        result = find_code_by_source("unknown_category", "contract")
        assert result is None


# ── find_code_by_name ─────────────────────────────────────────────


class TestFindCodeByName:
    def test_finds_code_by_keyword(self) -> None:
        result = find_code_by_name("non_litigation", "案卷封面")
        assert result is not None

    def test_returns_none_for_no_match(self) -> None:
        result = find_code_by_name("non_litigation", "不存在的关键词")
        assert result is None

    def test_returns_none_for_unknown_category(self) -> None:
        result = find_code_by_name("unknown_category", "test")
        assert result is None


# ── get_template_items ────────────────────────────────────────────


class TestGetTemplateItems:
    def test_returns_template_items(self) -> None:
        items = get_template_items("non_litigation")
        assert len(items) > 0
        for item in items:
            assert item["template"] is not None

    def test_unknown_category(self) -> None:
        items = get_template_items("unknown_category")
        assert items == []


# ── get_auto_detect_items ─────────────────────────────────────────


class TestGetAutoDetectItems:
    def test_returns_items_with_auto_detect(self) -> None:
        items = get_auto_detect_items("non_litigation")
        for item in items:
            assert item["auto_detect"] is not None

    def test_unknown_category(self) -> None:
        items = get_auto_detect_items("unknown_category")
        assert items == []


# ── _apply_subitem_order ──────────────────────────────────────────


class TestApplySubitemOrder:
    def test_no_details_no_error(self) -> None:
        _apply_subitem_order({})

    def test_single_item_no_sort(self) -> None:
        details = {"nl_4": [{"original_filename": "test.pdf", "order": 0}]}
        _apply_subitem_order(details)
        assert details["nl_4"][0]["original_filename"] == "test.pdf"

    def test_sorts_unordered_by_keyword(self) -> None:
        details = {
            "nl_4": [
                {"original_filename": "补充协议.pdf", "order": 0},
                {"original_filename": "委托合同.pdf", "order": 0},
            ]
        }
        _apply_subitem_order(details)
        # ARCHIVE_SUBITEM_ORDER_RULES["nl_4"] = ["委托合同", "合同正本"]
        # "委托合同" matches first keyword (index 0), "补充协议" matches nothing
        filenames = [d["original_filename"] for d in details["nl_4"]]
        assert filenames[0] == "委托合同.pdf"
        assert filenames[1] == "补充协议.pdf"

    def test_ordered_materials_not_resorted(self) -> None:
        details = {
            "nl_4": [
                {"original_filename": "补充协议.pdf", "order": 2},
                {"original_filename": "委托合同.pdf", "order": 1},
            ]
        }
        _apply_subitem_order(details)
        # All materials have order > 0, no re-sorting
        assert details["nl_4"][0]["order"] == 2

    def test_mixed_ordered_and_unordered(self) -> None:
        details = {
            "nl_4": [
                {"original_filename": "manual.pdf", "order": 3},
                {"original_filename": "补充协议.pdf", "order": 0},
                {"original_filename": "委托合同.pdf", "order": 0},
            ]
        }
        _apply_subitem_order(details)
        # Ordered stays first, then unordered are sorted
        assert details["nl_4"][0]["order"] == 3  # manual still first
        filenames = [d["original_filename"] for d in details["nl_4"][1:]]
        assert filenames[0] == "委托合同.pdf"
        assert filenames[1] == "补充协议.pdf"

    def test_no_unordered_materials(self) -> None:
        details = {
            "nl_4": [
                {"original_filename": "a.pdf", "order": 1},
                {"original_filename": "b.pdf", "order": 2},
            ]
        }
        _apply_subitem_order(details)
        # No unordered => no re-sorting
        assert details["nl_4"][0]["original_filename"] == "a.pdf"


# ── match_type_name_to_code ───────────────────────────────────────


class TestMatchTypeNameToCode:
    def test_match_first_keyword(self) -> None:
        keyword_map = {"code_a": ["授权", "委托书"], "code_b": ["起诉", "上诉"]}
        result = match_type_name_to_code("授权委托书", keyword_map)
        assert result == "code_a"

    def test_match_second_code(self) -> None:
        keyword_map = {"code_a": ["授权"], "code_b": ["起诉", "上诉"]}
        result = match_type_name_to_code("起诉状", keyword_map)
        assert result == "code_b"

    def test_no_match(self) -> None:
        keyword_map = {"code_a": ["授权"], "code_b": ["起诉"]}
        result = match_type_name_to_code("判决书", keyword_map)
        assert result is None

    def test_empty_type_name(self) -> None:
        keyword_map = {"code_a": ["授权"]}
        result = match_type_name_to_code("", keyword_map)
        assert result is None

    def test_empty_keyword_map(self) -> None:
        result = match_type_name_to_code("授权", {})
        assert result is None


# ── fill_material_details_from_ids ────────────────────────────────


class TestFillMaterialDetailsFromIds:
    def test_fills_new_materials(self) -> None:
        mat = MagicMock()
        mat.id = 1
        mat.original_filename = "test.pdf"
        mat.category = MaterialCategory.ARCHIVE_UPLOAD
        mat.order = 0
        mat.file_path = "path/to/test.pdf"

        details: dict[str, list[dict[str, Any]]] = {}
        code_to_ids = {"code_a": [1]}

        fill_material_details_from_ids(details, code_to_ids, [mat])
        assert len(details["code_a"]) == 1
        assert details["code_a"][0]["id"] == 1
        assert details["code_a"][0]["source"] == "upload"

    def test_skips_existing_id(self) -> None:
        mat = MagicMock()
        mat.id = 1
        mat.original_filename = "test.pdf"
        mat.category = MaterialCategory.ARCHIVE_UPLOAD
        mat.order = 0
        mat.file_path = "path/to/test.pdf"

        details: dict[str, list[dict[str, Any]]] = {
            "code_a": [{"id": 1}]
        }
        code_to_ids = {"code_a": [1]}

        fill_material_details_from_ids(details, code_to_ids, [mat])
        assert len(details["code_a"]) == 1  # Not duplicated

    def test_missing_material_object_skipped(self) -> None:
        details: dict[str, list[dict[str, Any]]] = {}
        code_to_ids = {"code_a": [999]}  # ID not in materials list

        fill_material_details_from_ids(details, code_to_ids, [])
        assert "code_a" not in details

    def test_multiple_codes(self) -> None:
        mat1 = MagicMock()
        mat1.id = 1
        mat1.original_filename = "a.pdf"
        mat1.category = MaterialCategory.CONTRACT_ORIGINAL
        mat1.order = 0
        mat1.file_path = "a.pdf"

        mat2 = MagicMock()
        mat2.id = 2
        mat2.original_filename = "b.pdf"
        mat2.category = MaterialCategory.INVOICE
        mat2.order = 1
        mat2.file_path = "b.pdf"

        details: dict[str, list[dict[str, Any]]] = {}
        code_to_ids = {"code_a": [1], "code_b": [2]}

        fill_material_details_from_ids(details, code_to_ids, [mat1, mat2])
        assert len(details["code_a"]) == 1
        assert len(details["code_b"]) == 1
        assert details["code_a"][0]["source"] == "contract"
        assert details["code_b"][0]["source"] == "contract"
