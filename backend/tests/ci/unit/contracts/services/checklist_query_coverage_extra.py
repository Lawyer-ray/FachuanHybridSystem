"""Unit tests for contracts.services.archive.checklist.checklist_query."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from apps.contracts.models.finalized_material import MaterialCategory


# ============================================================
# get_template_items
# ============================================================


class TestGetTemplateItems:
    """get_template_items tests."""

    def test_filters_template_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items

        checklist = [
            {"code": "t1", "name": "封面", "template": "case_cover", "required": True, "auto_detect": None,
             "source": "template"},
            {"code": "t2", "name": "正本", "template": None, "required": True, "auto_detect": None,
             "source": "contract"},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_template_items("litigation")
            assert len(result) == 1
            assert result[0]["code"] == "t1"

    def test_empty_when_no_templates(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items

        checklist = [
            {"code": "t1", "name": "正本", "template": None, "required": True, "auto_detect": None,
             "source": "contract"},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_template_items("litigation")
            assert result == []

    def test_unknown_category(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items

        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {},
        ):
            result = get_template_items("nonexistent")
            assert result == []


# ============================================================
# get_auto_detect_items
# ============================================================


class TestGetAutoDetectItems:
    """get_auto_detect_items tests."""

    def test_filters_auto_detect_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items

        checklist = [
            {"code": "a1", "name": "合同正本", "template": None, "required": True, "auto_detect": "filename",
             "source": "contract"},
            {"code": "a2", "name": "其他", "template": None, "required": False, "auto_detect": None,
             "source": "upload"},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_auto_detect_items("litigation")
            assert len(result) == 1
            assert result[0]["code"] == "a1"

    def test_empty_when_no_auto_detect(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items

        checklist = [
            {"code": "a1", "name": "其他", "template": None, "required": False, "auto_detect": None,
             "source": "upload"},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_auto_detect_items("litigation")
            assert result == []


# ============================================================
# _get_source
# ============================================================


class TestGetSource:
    """_get_source tests."""

    def test_contract_original(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.CONTRACT_ORIGINAL) == "contract"

    def test_supplementary_agreement(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.SUPPLEMENTARY_AGREEMENT) == "contract"

    def test_invoice(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.INVOICE) == "contract"

    def test_archive_document(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.ARCHIVE_DOCUMENT) == "auto"

    def test_supervision_card(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.SUPERVISION_CARD) == "upload"

    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.AUTHORIZATION_MATERIAL) == "case"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.CASE_MATERIAL) == "case"

    def test_archive_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source(MaterialCategory.ARCHIVE_UPLOAD) == "upload"

    def test_unknown_returns_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source("unknown_category") == "upload"


# ============================================================
# _get_source_label
# ============================================================


class TestGetSourceLabel:
    """_get_source_label tests."""

    def test_contract_original(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.CONTRACT_ORIGINAL) == "合同正本"

    def test_supplementary_agreement(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.SUPPLEMENTARY_AGREEMENT) == "补充协议"

    def test_invoice(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.INVOICE) == "发票"

    def test_archive_document(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.ARCHIVE_DOCUMENT) == "自动生成"

    def test_supervision_card(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.SUPERVISION_CARD) == "监督卡"

    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.AUTHORIZATION_MATERIAL) == "授权委托"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.CASE_MATERIAL) == "案件同步"

    def test_archive_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label(MaterialCategory.ARCHIVE_UPLOAD) == "手动上传"

    def test_unknown_returns_manual(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label("unknown") == "手动上传"


# ============================================================
# _apply_subitem_order
# ============================================================


class TestApplySubitemOrder:
    """_apply_subitem_order tests."""

    def test_no_details_no_error(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        _apply_subitem_order({})

    def test_single_detail_no_reorder(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        details = {"code1": [{"order": 0, "original_filename": "test.pdf"}]}
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_SUBITEM_ORDER_RULES",
            {"code1": ("test",)},
        ):
            _apply_subitem_order(details)
            assert details["code1"][0]["original_filename"] == "test.pdf"

    def test_orders_unordered_by_keyword(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        details = {
            "code1": [
                {"order": 0, "original_filename": "乙起诉状.pdf"},
                {"order": 0, "original_filename": "甲起诉状.pdf"},
            ]
        }
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_SUBITEM_ORDER_RULES",
            {"code1": ("甲", "乙")},
        ):
            _apply_subitem_order(details)
            assert details["code1"][0]["original_filename"] == "甲起诉状.pdf"
            assert details["code1"][1]["original_filename"] == "乙起诉状.pdf"

    def test_ordered_items_stay_at_top(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order

        details = {
            "code1": [
                {"order": 0, "original_filename": "乙.pdf"},
                {"order": 1, "original_filename": "甲.pdf"},
            ]
        }
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_SUBITEM_ORDER_RULES",
            {"code1": ("甲", "乙")},
        ):
            _apply_subitem_order(details)
            assert details["code1"][0]["order"] == 1
            assert details["code1"][1]["order"] == 0


# ============================================================
# get_checklist_with_status (partial coverage via mocks)
# ============================================================


class TestGetChecklistWithStatus:
    """get_checklist_with_status basic flow tests."""

    def test_returns_expected_structure(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_checklist_with_status

        mock_contract = MagicMock()
        mock_contract.compact_archive = False
        mock_contract.case_type = "civil"

        checklist = [
            {"code": "c1", "name": "合同正本", "source": "contract", "template": None,
             "required": True, "auto_detect": None},
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
            assert "items" in result
            assert "completed_count" in result
            assert "completion_percentage" in result
            assert result["archive_category"] == "litigation"

    def test_compact_archive_filters_uncompleted(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_checklist_with_status

        mock_contract = MagicMock()
        mock_contract.compact_archive = True
        mock_contract.case_type = "civil"

        checklist = [
            {"code": "c1", "name": "合同正本", "source": "contract", "template": None,
             "required": True, "auto_detect": None},
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
            assert result["total_count"] == 0
            assert result["completion_percentage"] == 0
