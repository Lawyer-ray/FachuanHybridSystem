"""Tests for checklist_query.py — additional coverage for get_checklist_with_status
and _apply_subitem_order with more edge cases.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── get_checklist_with_status: compact_archive ───────────────────


class TestGetChecklistWithStatusCompact:
    def test_compact_archive_completed_only(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import (
            get_checklist_with_status,
        )

        mock_contract = MagicMock()
        mock_contract.compact_archive = True
        mock_contract.case_type = "civil"

        checklist = [
            {"code": "c1", "name": "A", "source": "contract", "template": None,
             "required": True, "auto_detect": None},
            {"code": "c2", "name": "B", "source": "case", "template": None,
             "required": False, "auto_detect": None},
        ]

        mat = MagicMock()
        mat.id = 1
        mat.archive_item_code = "c1"
        mat.original_filename = "a.pdf"
        mat.category = "CONTRACT_ORIGINAL"
        mat.order = 0
        mat.file_path = "a.pdf"

        with (
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
                {"litigation": checklist},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_contract_materials",
                return_value={"c1": [1]},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_case_authorization_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_supervision_card_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.fill_material_details_from_ids",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.find_case_material_match_codes",
                return_value=set(),
            ),
        ):
            mock_fm.objects.filter.return_value.only.return_value.order_by.return_value = [mat]
            result = get_checklist_with_status(mock_contract)

            # compact_archive=True: only non-template completed items shown
            # c1 is completed, c2 is not — c2 should be filtered out
            assert result["total_count"] == 1
            assert result["completed_count"] == 1

    def test_completion_percentage_zero_total(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import (
            get_checklist_with_status,
        )

        mock_contract = MagicMock()
        mock_contract.compact_archive = False
        mock_contract.case_type = "civil"

        checklist = [
            {"code": "c1", "name": "A", "source": "template",
             "template": "tpl", "required": True, "auto_detect": None},
        ]

        with (
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
                {"litigation": checklist},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_contract_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_case_authorization_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_supervision_card_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.fill_material_details_from_ids",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.find_case_material_match_codes",
                return_value=set(),
            ),
        ):
            mock_fm.objects.filter.return_value.only.return_value.order_by.return_value = []
            result = get_checklist_with_status(mock_contract)
            # Template items filtered out → total_count = 0 → percentage = 0
            assert result["total_count"] == 0
            assert result["completion_percentage"] == 0


# ── get_checklist_with_status: materials with details ────────────


class TestGetChecklistWithStatusMaterials:
    def test_materials_attached_to_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import (
            get_checklist_with_status,
        )

        mock_contract = MagicMock()
        mock_contract.compact_archive = False
        mock_contract.case_type = "civil"

        checklist = [
            {"code": "c1", "name": "A", "source": "contract", "template": None,
             "required": True, "auto_detect": None},
        ]

        mat = MagicMock()
        mat.id = 5
        mat.archive_item_code = "c1"
        mat.original_filename = "test.pdf"
        mat.category = "CONTRACT_ORIGINAL"
        mat.order = 0
        mat.file_path = "path/to/test.pdf"

        with (
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
                {"litigation": checklist},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.FinalizedMaterial"
            ) as mock_fm,
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_contract_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_case_authorization_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.map_supervision_card_materials",
                return_value={},
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.fill_material_details_from_ids",
            ),
            patch(
                "apps.contracts.services.archive.checklist.checklist_query.find_case_material_match_codes",
                return_value=set(),
            ),
        ):
            mock_fm.objects.filter.return_value.only.return_value.order_by.return_value = [mat]
            result = get_checklist_with_status(mock_contract)
            assert result["completed_count"] == 1
            item = result["items"][0]
            assert item["completed"] is True
            assert 5 in item["material_ids"]


# ── _apply_subitem_order: edge cases ─────────────────────────────


class TestApplySubitemOrderEdge:
    def test_no_matching_keywords(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        details = {
            "code1": [
                {"order": 0, "original_filename": "xyz.pdf"},
                {"order": 0, "original_filename": "abc.pdf"},
            ]
        }
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_SUBITEM_ORDER_RULES",
            {"code1": ("甲", "乙")},
        ):
            _apply_subitem_order(details)
            # No keyword matches → original order preserved
            assert details["code1"][0]["original_filename"] == "xyz.pdf"

    def test_code_not_in_rules(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        details = {
            "other_code": [
                {"order": 0, "original_filename": "a.pdf"},
            ]
        }
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_SUBITEM_ORDER_RULES",
            {"different_code": ("keyword",)},
        ):
            _apply_subitem_order(details)
            assert details["other_code"][0]["original_filename"] == "a.pdf"


# ── _get_source_label: all MaterialCategory values ───────────────


class TestGetSourceLabelAll:
    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source_label(MaterialCategory.AUTHORIZATION_MATERIAL) == "授权委托"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source_label(MaterialCategory.CASE_MATERIAL) == "案件同步"

    def test_archive_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source_label(MaterialCategory.ARCHIVE_UPLOAD) == "手动上传"


# ── _get_source: all MaterialCategory values ─────────────────────


class TestGetSourceAll:
    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source(MaterialCategory.AUTHORIZATION_MATERIAL) == "case"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source(MaterialCategory.CASE_MATERIAL) == "case"
