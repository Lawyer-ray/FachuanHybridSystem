"""测试归档检查清单查询工具方法

覆盖: apps/contracts/services/archive/checklist/checklist_query.py
重点: find_code_by_source, find_code_by_name, get_template_items,
      get_auto_detect_items, _get_source, _get_source_label
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.contracts.models.finalized_material import MaterialCategory


# ============================================================
# find_code_by_source
# ============================================================


class TestFindCodeBySource:
    """测试根据 source 查找清单 code"""

    def test_finds_contract_source_with_keyword(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source

        checklist = [
            {"code": "lt_5", "name": "授权委托书", "source": "contract", "template": None, "required": True, "auto_detect": None},
            {"code": "lt_6", "name": "合同正本", "source": "contract", "template": None, "required": True, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = find_code_by_source("litigation", "contract")
            assert result == "lt_5"  # "委托" matches in "授权委托书"

    def test_returns_none_when_no_match(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source

        checklist = [
            {"code": "lt_1", "name": "封面", "source": "template", "template": "case_cover", "required": True, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = find_code_by_source("litigation", "contract")
            assert result is None

    def test_empty_checklist(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source

        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {},
        ):
            result = find_code_by_source("litigation", "contract")
            assert result is None


# ============================================================
# find_code_by_name
# ============================================================


class TestFindCodeByName:
    """测试根据名称关键词查找清单 code"""

    def test_finds_by_keyword(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name

        checklist = [
            {"code": "lt_7", "name": "收费凭证", "source": "contract", "template": None, "required": False, "auto_detect": None},
            {"code": "lt_8", "name": "其他材料", "source": "case", "template": None, "required": False, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = find_code_by_name("litigation", "收费凭证")
            assert result == "lt_7"

    def test_partial_match(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name

        checklist = [
            {"code": "lt_7", "name": "收费凭证及发票", "source": "contract", "template": None, "required": False, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = find_code_by_name("litigation", "收费")
            assert result == "lt_7"

    def test_no_match_returns_none(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name

        checklist = [
            {"code": "lt_7", "name": "收费凭证", "source": "contract", "template": None, "required": False, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = find_code_by_name("litigation", "判决书")
            assert result is None


# ============================================================
# get_template_items
# ============================================================


class TestGetTemplateItems:
    """测试获取模板清单项"""

    def test_filters_template_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items

        checklist = [
            {"code": "lt_1", "name": "封面", "source": "template", "template": "case_cover", "required": True, "auto_detect": None},
            {"code": "lt_5", "name": "合同", "source": "contract", "template": None, "required": True, "auto_detect": None},
            {"code": "lt_2", "name": "登记表", "source": "template", "template": "register", "required": True, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_template_items("litigation")
            assert len(result) == 2
            assert all(item["template"] is not None for item in result)

    def test_empty_checklist(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items

        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {},
        ):
            result = get_template_items("litigation")
            assert result == []


# ============================================================
# get_auto_detect_items
# ============================================================


class TestGetAutoDetectItems:
    """测试获取自动检测清单项"""

    def test_filters_auto_detect_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items

        checklist = [
            {"code": "lt_10", "name": "监督卡", "source": "upload", "template": None, "required": False, "auto_detect": "supervision_card"},
            {"code": "lt_1", "name": "封面", "source": "template", "template": "case_cover", "required": True, "auto_detect": None},
        ]
        with patch(
            "apps.contracts.services.archive.checklist.checklist_query.ARCHIVE_CHECKLIST",
            {"litigation": checklist},
        ):
            result = get_auto_detect_items("litigation")
            assert len(result) == 1
            assert result[0]["auto_detect"] == "supervision_card"


# ============================================================
# _get_source_label
# ============================================================


class TestGetSourceLabel:
    """测试材料来源标签"""

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

    def test_unknown_defaults_to_manual(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label

        assert _get_source_label("unknown_category") == "手动上传"


# ============================================================
# _get_source
# ============================================================


class TestGetSource:
    """测试材料来源类型"""

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

    def test_unknown_defaults_to_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source

        assert _get_source("unknown_category") == "upload"
