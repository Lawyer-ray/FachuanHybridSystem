"""Final push coverage tests for documents module — placeholders, archive."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, PropertyMock, patch

import pytest


# ============================================================================
# documents/services/placeholders/archive/__init__.py tests
# ============================================================================


class TestArchiveMaterialsRichText:
    def test_add_and_plain_text(self):
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("第一项")
        rt.add("第二项")
        assert rt.plain_text == "第一项第二项"

    def test_add_break(self):
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("第一项")
        rt.add_break()
        rt.add("第二项")
        assert "\n" in rt.plain_text
        assert "第一项\n第二项" == rt.plain_text

    def test_str(self):
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("text")
        assert str(rt) == "text"

    def test_empty(self):
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        assert rt.plain_text == ""
        assert str(rt) == ""


class TestUnwrapArchiveRichText:
    def test_replaces_rich_text_with_listing(self):
        from apps.documents.services.placeholders.archive import (
            _ArchiveMaterialsRichText,
            unwrap_archive_rich_text,
        )

        rt = _ArchiveMaterialsRichText()
        rt.add("材料1")
        rt.add_break()
        rt.add("材料2")

        context = {"结案归档材料": rt, "其他": "字符串"}
        result = unwrap_archive_rich_text(context)
        # The rich text should be replaced with a Listing
        assert "其他" in result
        assert result["其他"] == "字符串"
        # The rich text key should now be a Listing object
        from docxtpl import Listing

        assert isinstance(result["结案归档材料"], Listing)

    def test_no_rich_text_keys(self):
        from apps.documents.services.placeholders.archive import unwrap_archive_rich_text

        context = {"key1": "value1", "key2": 42}
        result = unwrap_archive_rich_text(context)
        assert result == context

    def test_preserves_non_rich_text_values(self):
        from apps.documents.services.placeholders.archive import unwrap_archive_rich_text

        context = {"str_key": "text", "int_key": 123, "list_key": [1, 2]}
        result = unwrap_archive_rich_text(context)
        assert result["str_key"] == "text"
        assert result["int_key"] == 123
        assert result["list_key"] == [1, 2]


class TestArchivePlaceholderService:
    def test_format_chinese_date(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._format_chinese_date(date(2024, 1, 15))
        assert result == "2024年01月15日"

    def test_format_chinese_date_single_digit(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._format_chinese_date(date(2024, 6, 5))
        assert result == "2024年06月05日"

    def test_get_contract_name(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = Mock()
        contract.name = "测试合同"
        assert ArchivePlaceholderService._get_contract_name(contract) == "测试合同"

    def test_get_contract_name_empty(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = Mock(spec=[])
        assert ArchivePlaceholderService._get_contract_name(contract) == ""

    def test_get_contract_type_display(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = Mock()
        contract.get_case_type_display.return_value = "民商事"
        assert ArchivePlaceholderService._get_contract_type(contract) == "民商事"

    def test_get_contract_type_fallback(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = Mock()
        contract.get_case_type_display.side_effect = Exception("no display")
        contract.case_type = "civil"
        assert ArchivePlaceholderService._get_contract_type(contract) == "civil"

    def test_placeholder_keys_exist(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assert "主办律师姓名" in ArchivePlaceholderService.placeholder_keys
        assert "合同名称" in ArchivePlaceholderService.placeholder_keys
        assert "归档日期" in ArchivePlaceholderService.placeholder_keys
        assert "生成日期" in ArchivePlaceholderService.placeholder_keys
        assert "结案归档材料" in ArchivePlaceholderService.placeholder_keys

    def test_placeholder_metadata_exists(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assert "主办律师姓名" in ArchivePlaceholderService.placeholder_metadata
        assert "display_name" in ArchivePlaceholderService.placeholder_metadata["主办律师姓名"]

    def test_generate_no_case_no_contract(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()
        result = service.generate({})
        assert "归档日期" in result
        assert "生成日期" in result

    def test_generate_with_contract(self):
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        # Test the static helper methods directly to avoid ORM queries
        contract = type("MockContract", (), {
            "name": "测试合同",
            "case_type": "civil",
        })()

        assert ArchivePlaceholderService._get_contract_name(contract) == "测试合同"
        assert ArchivePlaceholderService._get_contract_type(contract) == "civil"

        # generate() with no args (no case, no contract) is safe
        service = ArchivePlaceholderService()
        result = service.generate({})
        assert "归档日期" in result
        assert "生成日期" in result
