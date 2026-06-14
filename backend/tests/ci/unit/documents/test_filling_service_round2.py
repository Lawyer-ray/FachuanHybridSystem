"""Round 2 coverage tests for FillingService — uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.external_template.filling_service import FillingService
from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE


def _make_service(**kwargs):
    defaults = {"placeholder_registry": MagicMock()}
    defaults.update(kwargs)
    return FillingService(**defaults)


def _mock_doc(paragraphs=None, tables=None):
    doc = MagicMock()
    doc.paragraphs = paragraphs if paragraphs is not None else []
    doc.tables = tables if tables is not None else []
    return doc


class TestWriteTextMultipleRuns:
    """Test _write_text with multiple runs (clears subsequent runs)."""

    def test_paragraph_multiple_runs_clears_subsequent(self):
        svc = _make_service()
        run1 = MagicMock()
        run1.text = "first"
        run2 = MagicMock()
        run2.text = "second"
        run3 = MagicMock()
        run3.text = "third"
        para = MagicMock()
        para.runs = [run1, run2, run3]
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_text(doc, {"type": "paragraph", "paragraph_index": 0}, "new")
        assert result is True
        assert run1.text == "new"
        assert run2.text == ""
        assert run3.text == ""

    def test_table_cell_multiple_runs_clears_subsequent(self):
        svc = _make_service()
        run1 = MagicMock()
        run1.text = "first"
        run2 = MagicMock()
        run2.text = "second"
        para = MagicMock()
        para.runs = [run1, run2]
        cell = MagicMock()
        cell.paragraphs = [para]
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])

        result = svc._write_text(doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "new")
        assert result is True
        assert run1.text == "new"
        assert run2.text == ""


class TestWriteDeleteInapplicableTableOutOfBounds:
    """Test _write_delete_inapplicable table cell out-of-bounds branches."""

    def test_table_index_out_of_bounds(self):
        svc = _make_service()
        doc = _mock_doc(tables=[])
        result = svc._write_delete_inapplicable(
            doc, {"type": "table_cell", "table_index": 5, "row": 0, "col": 0}, "A"
        )
        assert result is False

    def test_row_col_out_of_bounds(self):
        svc = _make_service()
        table = MagicMock()
        table.rows = []
        doc = _mock_doc(tables=[table])
        result = svc._write_delete_inapplicable(
            doc, {"type": "table_cell", "table_index": 0, "row": 5, "col": 0}, "A"
        )
        assert result is False

    def test_table_cell_no_paragraphs(self):
        svc = _make_service()
        cell = MagicMock()
        cell.paragraphs = []
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])
        result = svc._write_delete_inapplicable(
            doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "A"
        )
        # paragraph is None, returns False
        assert result is False

    def test_delete_inapplicable_locator_out_of_bounds(self):
        svc = _make_service()
        doc = _mock_doc(paragraphs=[])
        result = svc._write_delete_inapplicable(
            doc, {"type": "delete_inapplicable", "paragraph_index": 5}, "A"
        )
        assert result is False

    def test_unknown_locator_type(self):
        svc = _make_service()
        doc = _mock_doc()
        result = svc._write_delete_inapplicable(
            doc, {"type": "something_else"}, "A"
        )
        assert result is False


class TestWriteCheckboxOldFormat:
    """Test _write_checkbox with old format checkboxes."""

    def test_old_format_ff_checkbox(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w:ffData>
                        <w:checkBox>
                            <w:checked w:val="0"/>
                        </w:checkBox>
                    </w:ffData>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "true")
        assert result is True

    def test_old_format_ff_default_element(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w:ffData>
                        <w:checkBox>
                            <w:default w:val="1"/>
                        </w:checkBox>
                    </w:ffData>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "false")
        assert result is True

    def test_old_format_no_checked_element(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w:ffData>
                        <w:checkBox/>
                    </w:ffData>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "true")
        assert result is True


class TestWriteCheckboxW14NoChecked:
    """Test w14 checkbox with no checked element."""

    def test_w14_no_checked_element(self):
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w14:checkbox/>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "true")
        assert result is True


class TestGeneratePreviewWithPartyId:
    """Test generate_preview passes party_id to _get_placeholder_values."""

    def test_party_id_passed(self):
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = []
            with patch.object(svc, "_get_placeholder_values", return_value={}) as mock_gpv:
                svc.generate_preview(template_id=1, case_id=1, party_id=42)
                mock_gpv.assert_called_once_with(1, 42)


class TestFillTemplateCheckboxPath:
    """Test fill_template with checkbox fill_type."""

    def test_checkbox_fill_success(self):
        svc = _make_service()
        from apps.documents.services.external_template.filling_service import FillPreviewItem
        mapping = MagicMock()
        mapping.semantic_label = "chk"
        mapping.fill_type = "checkbox"
        mapping.position_locator = {"type": "checkbox", "checkbox_index": 0}
        mapping.position_description = "checkbox 0"

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            mock_tpl_obj = MagicMock()
            mock_tpl_obj.name = "tpl"
            mock_tpl.objects.get.return_value = mock_tpl_obj

            with patch("docx.Document") as mock_doc_cls:
                doc = MagicMock()
                doc.paragraphs = []
                doc.tables = []
                mock_doc_cls.return_value = doc

                with patch.object(svc, "_get_placeholder_values", return_value={"chk": "true"}), \
                     patch.object(svc, "_write_checkbox", return_value=True) as mock_wc, \
                     patch.object(svc, "_generate_output_filename", return_value="out.docx"), \
                     patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
                    mock_fr.objects.create.return_value = MagicMock(id=1)
                    svc.fill_template(template_id=1, case_id=1)
                    mock_wc.assert_called_once()


class TestFillTemplateDeleteInapplicablePath:
    """Test fill_template with delete_inapplicable fill_type."""

    def test_delete_inapplicable_fill_success(self):
        svc = _make_service()
        mapping = MagicMock()
        mapping.semantic_label = "dia"
        mapping.fill_type = "delete_inapplicable"
        mapping.position_locator = {"type": "paragraph", "paragraph_index": 0}
        mapping.position_description = "para 0"

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            mock_tpl_obj = MagicMock()
            mock_tpl_obj.name = "tpl"
            mock_tpl.objects.get.return_value = mock_tpl_obj

            with patch("docx.Document") as mock_doc_cls:
                doc = MagicMock()
                doc.paragraphs = []
                doc.tables = []
                mock_doc_cls.return_value = doc

                with patch.object(svc, "_get_placeholder_values", return_value={"dia": "A"}), \
                     patch.object(svc, "_write_delete_inapplicable", return_value=True) as mock_wdi, \
                     patch.object(svc, "_generate_output_filename", return_value="out.docx"), \
                     patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
                    mock_fr.objects.create.return_value = MagicMock(id=1)
                    svc.fill_template(template_id=1, case_id=1)
                    mock_wdi.assert_called_once()


class TestFillTemplateFalseResult:
    """Test fill_template when write returns False."""

    def test_write_false_records_skipped(self):
        svc = _make_service()
        mapping = MagicMock()
        mapping.semantic_label = "x"
        mapping.fill_type = "text"
        mapping.position_locator = {"type": "paragraph", "paragraph_index": 0}
        mapping.position_description = "para 0"

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            mock_tpl.objects.get.return_value = MagicMock(name="tpl")

            with patch("docx.Document") as mock_doc_cls:
                mock_doc_cls.return_value = MagicMock(paragraphs=[], tables=[])

                with patch.object(svc, "_get_placeholder_values", return_value={"x": "val"}), \
                     patch.object(svc, "_write_text", return_value=False), \
                     patch.object(svc, "_generate_output_filename", return_value="out.docx"), \
                     patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
                    mock_fr.objects.create.return_value = MagicMock(id=1)
                    svc.fill_template(template_id=1, case_id=1)

            create_kwargs = mock_fr.objects.create.call_args.kwargs
            report = create_kwargs["report_json"]
            assert report["skipped_count"] == 1
            assert report["filled_count"] == 0
            assert len(report["errors"]) > 0


class TestGetPlaceholderValuesMultipleServices:
    """Test _get_placeholder_values with multiple services."""

    def test_merges_values_from_multiple_services(self):
        svc = _make_service()
        svc1 = MagicMock()
        svc1.name = "svc1"
        svc1.get_placeholder_keys.return_value = ["key1"]
        svc1.generate.return_value = {"key1": "val1"}

        svc2 = MagicMock()
        svc2.name = "svc2"
        svc2.get_placeholder_keys.return_value = ["key2"]
        svc2.generate.return_value = {"key2": "val2"}

        svc._placeholder_registry.get_all_services.return_value = [svc1, svc2]
        result = svc._get_placeholder_values(case_id=1)
        assert result["key1"] == "val1"
        assert result["key2"] == "val2"

    def test_partial_exception_only_fills_failed_keys(self):
        svc = _make_service()
        svc1 = MagicMock()
        svc1.name = "svc1"
        svc1.get_placeholder_keys.return_value = ["key1"]
        svc1.generate.return_value = {"key1": "val1"}

        svc2 = MagicMock()
        svc2.name = "svc2"
        svc2.get_placeholder_keys.return_value = ["key2", "key3"]
        svc2.generate.side_effect = Exception("fail")

        svc._placeholder_registry.get_all_services.return_value = [svc1, svc2]
        result = svc._get_placeholder_values(case_id=1)
        assert result["key1"] == "val1"
        assert result["key2"] == PLACEHOLDER_FALLBACK_VALUE
        assert result["key3"] == PLACEHOLDER_FALLBACK_VALUE


class TestCheckFileAvailabilityUpdated:
    def test_changes_from_true_to_false(self):
        svc = _make_service()
        record = MagicMock()
        record.file_path = "doc.docx"
        record.file_available = True

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr, \
             patch("apps.documents.services.external_template.filling_service.Path") as MockPath:
            mock_fr.objects.get.return_value = record
            MockPath.return_value.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            result = svc.check_file_availability(1)

        assert result is False
        record.save.assert_called_once_with(update_fields=["file_available"])
