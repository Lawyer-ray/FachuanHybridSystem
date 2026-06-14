"""Round 2 coverage tests for AnalysisService — uncovered branches."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError

from apps.documents.services.external_template.analysis_service import AnalysisService


def _make_service(**kwargs):
    defaults = {
        "fingerprint_service": MagicMock(),
        "llm_service": MagicMock(),
        "placeholder_registry": MagicMock(),
    }
    defaults.update(kwargs)
    return AnalysisService(**defaults)


class TestExtractTables:
    """Test _extract_tables and _extract_single_table with more complex scenarios."""

    def test_empty_tables(self):
        svc = _make_service()
        doc = MagicMock()
        doc.tables = []
        result = svc._extract_tables(doc)
        assert result == []

    def test_single_table_with_text(self):
        svc = _make_service()
        # Build a mock table with XML structure
        table = MagicMock()
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        # Create XML tr/tc elements
        import xml.etree.ElementTree as ET
        tbl_xml = '''<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:tr>
                <w:tc><w:t>Cell1</w:t></w:tc>
                <w:tc><w:t>Cell2</w:t></w:tc>
            </w:tr>
        </w:tbl>'''
        table._tbl = ET.fromstring(tbl_xml)
        table.rows = [MagicMock()]
        table.rows[0].cells = [MagicMock(), MagicMock()]
        table.rows[0].cells[0].tables = []
        table.rows[0].cells[1].tables = []

        result = svc._extract_single_table(table, 0, [])
        assert result["table_index"] == 0
        assert len(result["rows"]) == 1
        assert len(result["rows"][0]["cells"]) == 2

    def test_merged_cells(self):
        svc = _make_service()
        import xml.etree.ElementTree as ET
        table = MagicMock()
        tbl_xml = '''<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:tr>
                <w:tc>
                    <w:tcPr><w:gridSpan w:val="2"/></w:tcPr>
                    <w:t>Merged</w:t>
                </w:tc>
                <w:tc><w:t>Normal</w:t></w:tc>
            </w:tr>
        </w:tbl>'''
        table._tbl = ET.fromstring(tbl_xml)
        table.rows = [MagicMock()]
        table.rows[0].cells = [MagicMock(), MagicMock()]
        table.rows[0].cells[0].tables = []

        result = svc._extract_single_table(table, 0, [])
        cells = result["rows"][0]["cells"]
        assert len(cells) == 2
        # First cell has col_span
        assert cells[0].get("col_span") == 2

    def test_vertical_merge_continue_skipped(self):
        svc = _make_service()
        import xml.etree.ElementTree as ET
        table = MagicMock()
        tbl_xml = '''<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:tr>
                <w:tc>
                    <w:tcPr><w:vMerge w:val="continue"/></w:tcPr>
                    <w:t>Continued</w:t>
                </w:tc>
            </w:tr>
        </w:tbl>'''
        table._tbl = ET.fromstring(tbl_xml)
        table.rows = [MagicMock()]
        table.rows[0].cells = []

        result = svc._extract_single_table(table, 0, [])
        # vMerge continue cells are skipped
        assert len(result["rows"][0]["cells"]) == 0

    def test_delete_inapplicable_in_table_cell(self):
        svc = _make_service()
        import xml.etree.ElementTree as ET
        table = MagicMock()
        tbl_xml = '''<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:tr>
                <w:tc><w:t>自然人/法人</w:t></w:tc>
            </w:tr>
        </w:tbl>'''
        table._tbl = ET.fromstring(tbl_xml)
        table.rows = [MagicMock()]
        table.rows[0].cells = [MagicMock()]
        table.rows[0].cells[0].tables = []

        result = svc._extract_single_table(table, 0, [])
        cell = result["rows"][0]["cells"][0]
        assert cell.get("delete_inapplicable") is not None


class TestExtractCheckboxesExtended:
    """Extended checkbox extraction tests."""

    def test_xml_parse_error(self):
        svc = _make_service()
        doc = MagicMock()
        doc.element.xml = "<<<invalid>>>"
        result = svc._extract_checkboxes(doc)
        assert result == []

    def test_w_checkbox_format(self):
        """Test w:checkbox (not w14:checkbox) format."""
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:sdt>
                <w:sdtPr>
                    <w:checkbox>
                        <w:checked w:val="1"/>
                    </w:checkbox>
                </w:sdtPr>
                <w:sdtContent>
                    <w:r><w:t>Opt1</w:t></w:r>
                </w:sdtContent>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert len(result) == 1
        assert result[0]["checked"] is True

    def test_no_sdt_content(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w14:checkbox>
                        <w14:checked w14:val="0"/>
                    </w14:checkbox>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert len(result) == 1
        assert result[0]["label"] == ""

    def test_sdt_without_sdt_pr(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:sdt>
                <w:sdtContent><w:r><w:t>x</w:t></w:r></w:sdtContent>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert result == []

    def test_sdt_not_checkbox(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:sdt>
                <w:sdtPr>
                    <w:date/>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert result == []


class TestDetectDeleteInapplicableExtended:
    def test_multiple_slashes(self):
        svc = _make_service()
        result = svc._detect_delete_inapplicable("甲方/乙方/丙方/丁方")
        assert result is not None
        assert len(result) == 4

    def test_no_slash(self):
        svc = _make_service()
        assert svc._detect_delete_inapplicable("没有斜杠的文本") is None

    def test_mixed_chinese_english(self):
        svc = _make_service()
        result = svc._detect_delete_inapplicable("原告/被告")
        assert result is not None
        assert "原告" in result

    def test_fullwidth_slash_multiple(self):
        svc = _make_service()
        result = svc._detect_delete_inapplicable("选项A／选项B／选项C")
        assert result is not None
        assert len(result) == 3


class TestParseLlmResponseExtended:
    def test_markdown_with_language_tag(self):
        svc = _make_service()
        data = [{"semantic_label": "x", "fill_type": "text", "position_locator": {}}]
        response = "```json\n" + json.dumps(data) + "\n```"
        result = svc._parse_llm_response(response)
        assert len(result) == 1

    def test_empty_list(self):
        svc = _make_service()
        result = svc._parse_llm_response("[]")
        assert result == []

    def test_item_without_optional_fields(self):
        svc = _make_service()
        result = svc._parse_llm_response('[{}]')
        assert len(result) == 1
        assert result[0]["semantic_label"] == ""
        assert result[0]["fill_type"] == "text"

    def test_markdown_no_closing_fence(self):
        svc = _make_service()
        data = [{"semantic_label": "x", "fill_type": "text", "position_locator": {}}]
        response = "```json\n" + json.dumps(data)
        result = svc._parse_llm_response(response)
        assert len(result) == 1


class TestCreateFieldMappingsExtended:
    def test_delete_inapplicable_type(self):
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "delete_inapplicable"}, "semantic_label": "dia", "fill_type": "delete_inapplicable"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._create_field_mappings(template, mappings)

        call_kwargs = mock_fm.objects.create.call_args[1]
        assert "删除不适用项" in call_kwargs["position_description"]

    def test_unknown_pos_type(self):
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "unknown"}, "semantic_label": "x", "fill_type": "text"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            svc._create_field_mappings(template, mappings)

        call_kwargs = mock_fm.objects.create.call_args[1]
        assert call_kwargs["position_description"] == ""


class TestAnalyzeTemplateFingerprintMatchExcludesSelf:
    def test_fingerprint_match_self_excluded_and_llm_called(self):
        svc = _make_service()
        template_obj = MagicMock()
        template_obj.pk = 1
        template_obj.file_path = "doc.docx"

        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl.objects.get.return_value = template_obj

            with patch.object(svc, "extract_structure", return_value={}), \
                 patch.object(svc._fingerprint_service, "compute_fingerprint", return_value="fp"), \
                 patch.object(svc._fingerprint_service, "find_matching_template", return_value=template_obj) as mock_find, \
                 patch.object(svc, "_build_llm_prompt", return_value="prompt") as mock_prompt, \
                 patch.object(svc._llm_service, "complete", return_value=MagicMock(content='[]')) as mock_complete, \
                 patch.object(svc, "_create_field_mappings", return_value=[]):
                result = svc.analyze_template(1)

        # self-match was excluded, should go through LLM path
        mock_complete.assert_called_once()
        mock_prompt.assert_called_once()
