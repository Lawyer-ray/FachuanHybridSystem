"""
Unit tests for FillingService.

Covers:
  - __init__
  - generate_preview (auto, manual, empty fallback, no mappings)
  - get_custom_fields
  - _get_placeholder_values (normal, exception, with party_id)
  - fill_template (text, checkbox, delete_inapplicable, unknown type, exception, no party)
  - _write_text (paragraph, table_cell, out of bounds, no runs, unknown type)
  - _write_checkbox (w14 checked, unchecked, old format, out of bounds, exception)
  - _write_delete_inapplicable (paragraph, table_cell, delete_inapplicable type, exception)
  - _generate_output_filename (with party, without party)
  - batch_fill (success, failure, no records)
  - _pack_to_zip (normal, no records, missing files)
  - get_fill_history_by_case / get_fill_history_by_template
  - re_fill
  - check_file_availability (exists, not exists)
  - save_custom_values (existing record, no record)
  - load_custom_values (existing, none)
  - FillPreviewItem / FillReport dataclasses
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.documents.services.external_template.filling_service import (
    FillingService,
    FillPreviewItem,
    FillReport,
)
from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs: Any) -> FillingService:
    defaults = {"placeholder_registry": MagicMock()}
    defaults.update(kwargs)
    return FillingService(**defaults)


def _make_mapping(
    semantic_label: str = "name",
    fill_type: str = "text",
    position_locator: dict | None = None,
    position_description: str = "para 0",
    sort_order: int = 0,
    mapping_id: int = 1,
) -> MagicMock:
    m = MagicMock()
    m.semantic_label = semantic_label
    m.fill_type = fill_type
    m.position_locator = position_locator or {"type": "paragraph", "paragraph_index": 0}
    m.position_description = position_description
    m.sort_order = sort_order
    m.id = mapping_id
    return m


def _mock_doc(paragraphs: list | None = None, tables: list | None = None) -> MagicMock:
    doc = MagicMock()
    doc.paragraphs = paragraphs if paragraphs is not None else []
    doc.tables = tables if tables is not None else []
    return doc


# ===========================================================================
# Dataclass tests
# ===========================================================================


class TestFillPreviewItem:
    def test_fields(self) -> None:
        item = FillPreviewItem(
            position_description="p",
            semantic_label="l",
            fill_value="v",
            value_source="auto",
            fill_type="text",
            mapping_id=1,
        )
        assert item.position_description == "p"
        assert item.value_source == "auto"

    def test_immutable(self) -> None:
        item = FillPreviewItem("p", "l", "v", "auto", "text", 1)
        with pytest.raises(AttributeError):
            item.position_description = "x"  # type: ignore[misc]


class TestFillReport:
    def test_fields(self) -> None:
        report = FillReport(total_fields=5, filled_count=3, skipped_count=1, manual_needed=["a"], errors=[])
        assert report.total_fields == 5


# ===========================================================================
# Preview
# ===========================================================================


class TestGeneratePreview:
    def test_auto_value(self) -> None:
        svc = _make_service()
        mapping = _make_mapping(semantic_label="name")

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            with patch.object(svc, "_get_placeholder_values", return_value={"name": "张三"}):
                result = svc.generate_preview(template_id=1, case_id=1)

        assert len(result) == 1
        assert result[0].fill_value == "张三"
        assert result[0].value_source == "auto"

    def test_manual_value(self) -> None:
        svc = _make_service()
        mapping = _make_mapping(semantic_label="extra")

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            with patch.object(svc, "_get_placeholder_values", return_value={}):
                result = svc.generate_preview(
                    template_id=1, case_id=1, custom_values={"extra": "custom_val"}
                )

        assert result[0].fill_value == "custom_val"
        assert result[0].value_source == "manual"

    def test_empty_fallback(self) -> None:
        svc = _make_service()
        mapping = _make_mapping(semantic_label="missing")

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            with patch.object(svc, "_get_placeholder_values", return_value={}):
                result = svc.generate_preview(template_id=1, case_id=1)

        assert result[0].fill_value == PLACEHOLDER_FALLBACK_VALUE
        assert result[0].value_source == "empty"

    def test_no_mappings(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = []
            with patch.object(svc, "_get_placeholder_values", return_value={}):
                result = svc.generate_preview(template_id=1, case_id=1)
        assert result == []


class TestGetCustomFields:
    def test_normal(self) -> None:
        svc = _make_service()
        m1 = _make_mapping(semantic_label="name", fill_type="text", position_description="p1", mapping_id=1)

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = [m1]
            result = svc.get_custom_fields(template_id=1)

        assert len(result) == 1
        assert result[0]["mapping_id"] == 1
        assert result[0]["semantic_label"] == "name"


# ===========================================================================
# Placeholder values
# ===========================================================================


class TestGetPlaceholderValues:
    def test_normal(self) -> None:
        svc = _make_service()
        mock_service = MagicMock()
        mock_service.name = "svc1"
        mock_service.get_placeholder_keys.return_value = ["key1"]
        mock_service.generate.return_value = {"key1": "value1"}

        svc._placeholder_registry.get_all_services.return_value = [mock_service]
        result = svc._get_placeholder_values(case_id=1)
        assert result["key1"] == "value1"

    def test_with_party_id(self) -> None:
        svc = _make_service()
        mock_service = MagicMock()
        mock_service.name = "svc1"
        mock_service.get_placeholder_keys.return_value = ["k"]
        mock_service.generate.return_value = {"k": "v"}
        svc._placeholder_registry.get_all_services.return_value = [mock_service]

        result = svc._get_placeholder_values(case_id=1, party_id=10)
        mock_service.generate.assert_called_once_with({"case_id": 1, "party_id": 10})

    def test_exception_fills_fallback(self) -> None:
        svc = _make_service()
        mock_service = MagicMock()
        mock_service.name = "svc1"
        mock_service.get_placeholder_keys.return_value = ["key1"]
        mock_service.generate.side_effect = Exception("svc error")
        svc._placeholder_registry.get_all_services.return_value = [mock_service]

        result = svc._get_placeholder_values(case_id=1)
        assert result["key1"] == PLACEHOLDER_FALLBACK_VALUE


# ===========================================================================
# Write methods
# ===========================================================================


class TestWriteText:
    def test_paragraph_normal(self) -> None:
        svc = _make_service()
        run = MagicMock()
        run.text = "old"
        para = MagicMock()
        para.runs = [run]
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_text(doc, {"type": "paragraph", "paragraph_index": 0}, "new")
        assert result is True
        assert run.text == "new"

    def test_paragraph_no_runs(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.runs = []
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_text(doc, {"type": "paragraph", "paragraph_index": 0}, "val")
        assert result is True
        para.add_run.assert_called_once_with("val")

    def test_paragraph_out_of_bounds(self) -> None:
        svc = _make_service()
        doc = _mock_doc(paragraphs=[])
        result = svc._write_text(doc, {"type": "paragraph", "paragraph_index": 5}, "val")
        assert result is False

    def test_table_cell_normal(self) -> None:
        svc = _make_service()
        run = MagicMock()
        run.text = "old"
        para = MagicMock()
        para.runs = [run]
        cell = MagicMock()
        cell.paragraphs = [para]
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])

        result = svc._write_text(doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "new")
        assert result is True

    def test_table_cell_no_runs(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.runs = []
        cell = MagicMock()
        cell.paragraphs = [para]
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])

        result = svc._write_text(doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "val")
        assert result is True
        para.add_run.assert_called_once_with("val")

    def test_table_cell_no_paragraphs(self) -> None:
        svc = _make_service()
        cell = MagicMock()
        cell.paragraphs = []
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])

        result = svc._write_text(doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "val")
        assert result is True

    def test_table_cell_out_of_bounds(self) -> None:
        svc = _make_service()
        table = MagicMock()
        table.rows = []
        doc = _mock_doc(tables=[table])
        result = svc._write_text(doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "val")
        assert result is False

    def test_table_index_out_of_bounds(self) -> None:
        svc = _make_service()
        doc = _mock_doc(tables=[])
        result = svc._write_text(doc, {"type": "table_cell", "table_index": 5, "row": 0, "col": 0}, "val")
        assert result is False

    def test_unknown_type(self) -> None:
        svc = _make_service()
        doc = _mock_doc()
        result = svc._write_text(doc, {"type": "unknown"}, "val")
        assert result is False

    def test_exception(self) -> None:
        svc = _make_service()
        doc = MagicMock()
        doc.paragraphs.__len__ = MagicMock(side_effect=Exception("err"))
        result = svc._write_text(doc, {"type": "paragraph", "paragraph_index": 0}, "val")
        assert result is False


class TestWriteCheckbox:
    def test_w14_checked(self) -> None:
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
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "true")
        assert result is True

    def test_w14_unchecked(self) -> None:
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w14:checkbox>
                        <w14:checked w14:val="1"/>
                    </w14:checkbox>
                </w:sdtPr>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "false")
        assert result is True

    def test_out_of_bounds(self) -> None:
        svc = _make_service()
        doc = MagicMock()
        doc.element.xml = "<root/>"
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 5}, "true")
        assert result is False

    def test_exception(self) -> None:
        svc = _make_service()
        doc = MagicMock()
        doc.element.xml = "not xml"
        result = svc._write_checkbox(doc, {"type": "checkbox", "checkbox_index": 0}, "true")
        assert result is False


class TestWriteDeleteInapplicable:
    def test_paragraph_type(self) -> None:
        svc = _make_service()
        run = MagicMock()
        run.text = "A/B"
        para = MagicMock()
        para.runs = [run]
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_delete_inapplicable(
            doc, {"type": "paragraph", "paragraph_index": 0}, "A"
        )
        assert result is True
        assert run.text == "A"

    def test_table_cell_type(self) -> None:
        svc = _make_service()
        run = MagicMock()
        run.text = "X/Y"
        para = MagicMock()
        para.runs = [run]
        cell = MagicMock()
        cell.paragraphs = [para]
        table = MagicMock()
        table.rows = [MagicMock()]
        table.columns = [MagicMock()]
        table.cell.return_value = cell
        doc = _mock_doc(tables=[table])

        result = svc._write_delete_inapplicable(
            doc, {"type": "table_cell", "table_index": 0, "row": 0, "col": 0}, "X"
        )
        assert result is True

    def test_delete_inapplicable_locator_type(self) -> None:
        svc = _make_service()
        run = MagicMock()
        run.text = "A/B"
        para = MagicMock()
        para.runs = [run]
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_delete_inapplicable(
            doc, {"type": "delete_inapplicable", "paragraph_index": 0}, "A"
        )
        assert result is True

    def test_no_runs_paragraph(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.runs = []
        doc = _mock_doc(paragraphs=[para])

        result = svc._write_delete_inapplicable(
            doc, {"type": "paragraph", "paragraph_index": 0}, "A"
        )
        assert result is True
        para.add_run.assert_called_once_with("A")

    def test_out_of_bounds(self) -> None:
        svc = _make_service()
        doc = _mock_doc(paragraphs=[])
        result = svc._write_delete_inapplicable(
            doc, {"type": "paragraph", "paragraph_index": 5}, "A"
        )
        assert result is False

    def test_exception(self) -> None:
        svc = _make_service()
        doc = MagicMock()
        doc.paragraphs.__len__ = MagicMock(side_effect=Exception("err"))
        result = svc._write_delete_inapplicable(
            doc, {"type": "paragraph", "paragraph_index": 0}, "A"
        )
        assert result is False


# ===========================================================================
# Filename generation
# ===========================================================================


class TestGenerateOutputFilename:
    def test_with_party(self) -> None:
        svc = _make_service()
        assert svc._generate_output_filename("合同", "张三") == "合同_张三.docx"

    def test_without_party(self) -> None:
        svc = _make_service()
        assert svc._generate_output_filename("合同") == "合同.docx"

    def test_empty_party(self) -> None:
        svc = _make_service()
        assert svc._generate_output_filename("合同", None) == "合同.docx"


# ===========================================================================
# Fill template
# ===========================================================================


class TestFillTemplate:
    @patch("apps.documents.models.fill_record.FillRecord")
    @patch("apps.documents.models.external_template.ExternalTemplateFieldMapping")
    @patch("apps.documents.models.external_template.ExternalTemplate")
    @patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None))
    def test_text_mapping_success(
        self, mock_atomic: MagicMock, mock_tpl_cls: MagicMock, mock_fm_cls: MagicMock, mock_fr_cls: MagicMock
    ) -> None:
        svc = _make_service()
        mapping = _make_mapping(semantic_label="name", fill_type="text")
        mock_fm_cls.objects.filter.return_value.order_by.return_value = [mapping]
        mock_tpl_obj = MagicMock()
        mock_tpl_obj.name = "tpl1"
        mock_tpl_cls.objects.get.return_value = mock_tpl_obj

        run = MagicMock()
        run.text = "old"
        para = MagicMock()
        para.runs = [run]

        with patch("docx.Document") as mock_doc_cls:
            doc = MagicMock()
            doc.paragraphs = [para]
            doc.tables = []
            mock_doc_cls.return_value = doc

            with patch.object(svc, "_get_placeholder_values", return_value={"name": "张三"}), \
                 patch.object(svc, "_generate_output_filename", return_value="output.docx"), \
                 patch.object(svc, "_write_text", return_value=True) as mock_write:
                record = svc.fill_template(template_id=1, case_id=1)

        mock_write.assert_called_once()

    def test_unknown_fill_type_skips(self) -> None:
        svc = _make_service()
        mapping = _make_mapping(fill_type="unknown_type")

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            mock_tpl.objects.get.return_value = MagicMock(name="t")

            with patch("docx.Document") as mock_doc_cls:
                mock_doc_cls.return_value = MagicMock(paragraphs=[], tables=[])
                with patch.object(svc, "_get_placeholder_values", return_value={}):
                    with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
                        mock_fr.objects.create.return_value = MagicMock(id=1)
                        record = svc.fill_template(template_id=1, case_id=1)

        assert record is not None

    def test_write_exception_records_error(self) -> None:
        svc = _make_service()
        mapping = _make_mapping(semantic_label="x", fill_type="text")
        record_mock = MagicMock(id=1)

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_fm.objects.filter.return_value.order_by.return_value = [mapping]
            mock_tpl.objects.get.return_value = MagicMock(name="t")

            with patch("docx.Document") as mock_doc_cls:
                mock_doc_cls.return_value = MagicMock(paragraphs=[], tables=[])
                with patch.object(svc, "_get_placeholder_values", return_value={}):
                    with patch.object(svc, "_write_text", side_effect=Exception("write err")):
                        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
                            mock_fr.objects.create.return_value = record_mock
                            record = svc.fill_template(template_id=1, case_id=1)

        # report_json is passed as kwarg to FillRecord.objects.create()
        create_kwargs = mock_fr.objects.create.call_args.kwargs
        report = create_kwargs["report_json"]
        assert len(report["errors"]) > 0
        assert "写入失败" in report["errors"][0]


# ===========================================================================
# Batch fill
# ===========================================================================


class TestBatchFill:
    def test_single_success(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.id = 1
        record.batch_task_id = None
        record.case_id = 1
        record.report_json = {"filled_count": 1, "skipped_count": 0}
        record.file_path = "doc.docx"
        record.original_output_name = "out.docx"

        with patch("apps.documents.models.fill_record.BatchFillTask") as mock_batch, \
             patch.object(svc, "fill_template", return_value=record), \
             patch.object(svc, "_pack_to_zip", return_value="zip_path"), \
             patch("apps.documents.services.external_template.filling_service.timezone") as mock_tz:
            mock_tz.now.return_value = "now"
            mock_batch.objects.create.return_value = MagicMock(id=1, templates=MagicMock())
            result = svc.batch_fill(case_id=1, template_ids=[1])

        assert result is not None

    def test_failure_recorded(self) -> None:
        svc = _make_service()

        with patch("apps.documents.models.fill_record.BatchFillTask") as mock_batch, \
             patch.object(svc, "fill_template", side_effect=Exception("fail")), \
             patch("apps.documents.services.external_template.filling_service.timezone") as mock_tz:
            mock_tz.now.return_value = "now"
            mock_batch.objects.create.return_value = MagicMock(id=1, templates=MagicMock())
            result = svc.batch_fill(case_id=1, template_ids=[1])

        assert result.summary_json["failed"] == 1

    def test_no_records_no_zip(self) -> None:
        svc = _make_service()

        with patch("apps.documents.models.fill_record.BatchFillTask") as mock_batch, \
             patch.object(svc, "fill_template", side_effect=Exception("fail")), \
             patch("apps.documents.services.external_template.filling_service.timezone") as mock_tz:
            mock_tz.now.return_value = "now"
            mock_batch.objects.create.return_value = MagicMock(id=1, templates=MagicMock())
            result = svc.batch_fill(case_id=1, template_ids=[1], party_ids=[1])

        assert result.zip_file_path == ""


# ===========================================================================
# Pack to zip
# ===========================================================================


class TestPackToZip:
    def test_empty_records(self) -> None:
        svc = _make_service()
        assert svc._pack_to_zip([]) == ""

    def test_normal(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.case_id = 1
        record.batch_task_id = 10
        record.file_path = "doc.docx"
        record.original_output_name = "out.docx"

        with patch("pathlib.Path.exists", return_value=True), \
             patch("zipfile.ZipFile"):
            result = svc._pack_to_zip([record])

        assert "batch_10.zip" in result

    def test_missing_file(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.case_id = 1
        record.batch_task_id = 10
        record.file_path = "missing.docx"
        record.original_output_name = "out.docx"
        record.id = 42

        with patch("pathlib.Path.exists", return_value=False), \
             patch("zipfile.ZipFile"):
            result = svc._pack_to_zip([record])

        assert "batch_10.zip" in result


# ===========================================================================
# History and re-fill
# ===========================================================================


class TestFillHistory:
    def test_by_case(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.select_related.return_value.order_by.return_value = "qs"
            result = svc.get_fill_history_by_case(1)
        assert result == "qs"

    def test_by_template(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.select_related.return_value.order_by.return_value = "qs"
            result = svc.get_fill_history_by_template(1)
        assert result == "qs"


class TestReFill:
    def test_creates_new_record(self) -> None:
        svc = _make_service()
        old_record = MagicMock()
        old_record.template_id = 1
        old_record.case_id = 1
        old_record.party_id = 10
        old_record.custom_values = {"key": "val"}

        new_record = MagicMock(id=2)

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr, \
             patch.object(svc, "fill_template", return_value=new_record) as mock_fill:
            mock_fr.objects.get.return_value = old_record
            result = svc.re_fill(record_id=1)

            mock_fill.assert_called_once_with(
                template_id=1, case_id=1, party_id=10,
                custom_values={"key": "val"}, filled_by=None,
            )
            assert result is new_record


# ===========================================================================
# File availability
# ===========================================================================


class TestCheckFileAvailability:
    def test_file_exists(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.file_path = "doc.docx"
        record.file_available = False

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr, \
             patch("pathlib.Path.exists", return_value=True):
            mock_fr.objects.get.return_value = record
            result = svc.check_file_availability(1)

        assert result is True
        assert record.file_available is True
        record.save.assert_called()

    def test_file_not_exists(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.file_path = "doc.docx"
        record.file_available = True

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr, \
             patch("pathlib.Path.exists", return_value=False):
            mock_fr.objects.get.return_value = record
            result = svc.check_file_availability(1)

        assert result is False
        assert record.file_available is False
        record.save.assert_called()

    def test_no_change_no_save(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.file_path = "doc.docx"
        record.file_available = True

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr, \
             patch("pathlib.Path.exists", return_value=True):
            mock_fr.objects.get.return_value = record
            result = svc.check_file_availability(1)

        assert result is True
        record.save.assert_not_called()


# ===========================================================================
# Custom values
# ===========================================================================


class TestSaveCustomValues:
    def test_existing_record(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.custom_values = {"old": "val"}

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.order_by.return_value.first.return_value = record
            svc.save_custom_values(case_id=1, template_id=1, custom_values={"new": "val"})

        assert record.custom_values == {"new": "val"}
        record.save.assert_called_with(update_fields=["custom_values"])

    def test_no_existing_record(self) -> None:
        svc = _make_service()

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.order_by.return_value.first.return_value = None
            svc.save_custom_values(case_id=1, template_id=1, custom_values={"k": "v"})

        mock_fr.objects.create.assert_called_once()


class TestLoadCustomValues:
    def test_existing(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.custom_values = {"k": "v"}

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.order_by.return_value.first.return_value = record
            result = svc.load_custom_values(case_id=1, template_id=1)

        assert result == {"k": "v"}

    def test_no_record(self) -> None:
        svc = _make_service()

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.order_by.return_value.first.return_value = None
            result = svc.load_custom_values(case_id=1, template_id=1)

        assert result == {}

    def test_empty_custom_values(self) -> None:
        svc = _make_service()
        record = MagicMock()
        record.custom_values = {}

        with patch("apps.documents.models.fill_record.FillRecord") as mock_fr:
            mock_fr.objects.filter.return_value.order_by.return_value.first.return_value = record
            result = svc.load_custom_values(case_id=1, template_id=1)

        assert result == {}
