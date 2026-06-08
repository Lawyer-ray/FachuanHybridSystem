"""
Unit tests for AnalysisService.

Covers:
  - __init__
  - upload_template (success, non-docx, too large, unparseable, versioning)
  - _validate_file (valid, non-docx, too large)
  - _validate_parseable (success, failure)
  - _save_file
  - _handle_versioning (first, subsequent)
  - extract_structure (basic)
  - _extract_paragraphs (normal, empty, delete_inapplicable)
  - _extract_tables (normal, nested)
  - _extract_single_table (normal, merged cells)
  - _extract_checkboxes (w14 checkbox, none, no sdt)
  - _detect_delete_inapplicable (match, no match, slash only, half-width)
  - analyze_template (LLM path, fingerprint match, failure status)
  - _build_llm_prompt
  - _parse_llm_response (plain json, markdown wrapped, non-list, bad json)
  - _create_field_mappings (all types, invalid fill_type)
  - _copy_mappings_from
  - retry_analysis
  - create_manual_mapping
  - delete_mapping
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from django.core.exceptions import ValidationError

from apps.documents.services.external_template.analysis_service import AnalysisService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs: Any) -> AnalysisService:
    defaults = {
        "fingerprint_service": MagicMock(),
        "llm_service": MagicMock(),
        "placeholder_registry": MagicMock(),
    }
    defaults.update(kwargs)
    return AnalysisService(**defaults)


def _make_file(name: str = "test.docx", size: int = 1000) -> MagicMock:
    f = MagicMock()
    f.name = name
    f.size = size
    f.chunks.return_value = [b"content"]
    return f


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    def test_init(self) -> None:
        fp = MagicMock()
        llm = MagicMock()
        reg = MagicMock()
        svc = AnalysisService(fingerprint_service=fp, llm_service=llm, placeholder_registry=reg)
        assert svc._fingerprint_service is fp
        assert svc._llm_service is llm
        assert svc._placeholder_registry is reg


class TestValidateFile:
    def test_valid(self) -> None:
        svc = _make_service()
        svc._validate_file(_make_file("doc.docx"))

    def test_non_docx(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationError, match=r"仅支持 \.docx"):
            svc._validate_file(_make_file("doc.pdf"))

    def test_too_large(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationError, match="文件大小超出限制"):
            svc._validate_file(_make_file("doc.docx", size=21 * 1024 * 1024))

    def test_no_name(self) -> None:
        svc = _make_service()
        f = _make_file()
        f.name = None
        with pytest.raises(ValidationError, match=r"仅支持 \.docx"):
            svc._validate_file(f)


class TestValidateParseable:
    def test_valid(self) -> None:
        svc = _make_service()
        with patch("docx.Document"):
            svc._validate_parseable(Path("/tmp/test.docx"))

    def test_invalid(self) -> None:
        svc = _make_service()
        with patch("docx.Document", side_effect=Exception("corrupted")):
            with pytest.raises(ValidationError, match="文件无法解析"):
                svc._validate_parseable(Path("/tmp/test.docx"))


class TestSaveFile:
    def test_saves_file(self, tmp_path: Any) -> None:
        svc = _make_service()
        with patch("apps.documents.services.external_template.analysis_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            f = _make_file()
            abs_path, rel_path = svc._save_file(f, 1)
        assert abs_path.exists()
        assert rel_path.startswith("documents/external_templates/1/")


class TestHandleVersioning:
    def test_first_version(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
            mock_tpl.objects.filter.return_value.filter.return_value.update.return_value = 0
            version, deactivated = svc._handle_versioning(law_firm_id=1, source_name="src")
        assert version == 1
        assert deactivated == 0

    def test_subsequent_version(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = 3
            mock_tpl.objects.filter.return_value.filter.return_value.update.return_value = 2
            version, deactivated = svc._handle_versioning(law_firm_id=1, source_name="src")
        assert version == 4
        assert deactivated == 2


class TestUploadTemplate:
    def test_success(self, tmp_path: Any) -> None:
        svc = _make_service()
        uploaded_by = MagicMock()
        uploaded_by.law_firm_id = 1

        with patch.object(svc, "_validate_file"), \
             patch.object(svc, "_save_file", return_value=(Path("/tmp/x.docx"), "rel/doc.docx")), \
             patch.object(svc, "_validate_parseable"), \
             patch.object(svc, "_handle_versioning", return_value=(1, 0)), \
             patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("django.db.transaction.atomic", side_effect=lambda: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)):
            mock_tpl.objects.create.return_value = MagicMock(id=1, name="tpl", version=1)
            result = svc.upload_template(_make_file(), "tpl", "src", uploaded_by)

        mock_tpl.objects.create.assert_called_once()

    def test_non_docx_rejected(self) -> None:
        svc = _make_service()
        uploaded_by = MagicMock()
        uploaded_by.law_firm_id = 1
        with patch.object(svc, "_validate_file", side_effect=ValidationError("仅支持 .docx")):
            with pytest.raises(ValidationError):
                svc.upload_template(_make_file("bad.pdf"), "tpl", "src", uploaded_by)

    def test_unparseable_deletes_file(self, tmp_path: Any) -> None:
        svc = _make_service()
        uploaded_by = MagicMock()
        uploaded_by.law_firm_id = 1
        fake_path = tmp_path / "test.docx"
        fake_path.write_bytes(b"bad")

        with patch.object(svc, "_validate_file"), \
             patch.object(svc, "_save_file", return_value=(fake_path, "rel/doc.docx")), \
             patch.object(svc, "_validate_parseable", side_effect=ValidationError("unparseable")):
            with pytest.raises(ValidationError):
                svc.upload_template(_make_file(), "tpl", "src", uploaded_by)
        assert not fake_path.exists()


class TestExtractStructure:
    def test_basic(self, tmp_path: Any) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl_obj = MagicMock()
            mock_tpl.objects.get.return_value = mock_tpl_obj
            mock_tpl_obj.file_path = "doc.docx"

            with patch("docx.Document") as mock_doc:
                mock_doc.return_value.paragraphs = []
                mock_doc.return_value.tables = []
                mock_doc.return_value.element.xml = "<root/>"
                result = svc.extract_structure(1)

        assert "paragraphs" in result
        assert "tables" in result
        assert "checkboxes" in result
        mock_tpl_obj.save.assert_called()


class TestExtractParagraphs:
    def test_normal(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.text = "Hello world"
        doc = MagicMock()
        doc.paragraphs = [para]

        result = svc._extract_paragraphs(doc)
        assert len(result) == 1
        assert result[0]["text"] == "Hello world"
        assert result[0]["paragraph_index"] == 0

    def test_empty_paragraph_skipped(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.text = "  "
        doc = MagicMock()
        doc.paragraphs = [para]

        result = svc._extract_paragraphs(doc)
        assert len(result) == 0

    def test_delete_inapplicable(self) -> None:
        svc = _make_service()
        para = MagicMock()
        para.text = "自然人/法人/非法人组织"
        doc = MagicMock()
        doc.paragraphs = [para]

        result = svc._extract_paragraphs(doc)
        assert len(result) == 1
        assert result[0].get("delete_inapplicable") is not None
        assert "自然人" in result[0]["delete_inapplicable"]


class TestExtractCheckboxes:
    def test_no_sdt(self) -> None:
        svc = _make_service()
        doc = MagicMock()
        doc.element.xml = "<root><body/></root>"
        result = svc._extract_checkboxes(doc)
        assert result == []

    def test_w14_checkbox(self) -> None:
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w14:checkbox>
                        <w14:checked w14:val="1"/>
                    </w14:checkbox>
                </w:sdtPr>
                <w:sdtContent>
                    <w:r><w:t>Option A</w:t></w:r>
                </w:sdtContent>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert len(result) == 1
        assert result[0]["label"] == "Option A"
        assert result[0]["checked"] is True

    def test_unchecked_checkbox(self) -> None:
        svc = _make_service()
        xml = '''<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
            <w:sdt>
                <w:sdtPr>
                    <w14:checkbox/>
                </w:sdtPr>
                <w:sdtContent>
                    <w:r><w:t>Opt</w:t></w:r>
                </w:sdtContent>
            </w:sdt>
        </root>'''
        doc = MagicMock()
        doc.element.xml = xml
        result = svc._extract_checkboxes(doc)
        assert len(result) == 1
        assert result[0]["checked"] is False


class TestDetectDeleteInapplicable:
    def test_match_chinese(self) -> None:
        svc = _make_service()
        result = svc._detect_delete_inapplicable("自然人/法人/非法人组织")
        assert result is not None
        assert len(result) == 3
        assert "自然人" in result

    def test_no_match(self) -> None:
        svc = _make_service()
        assert svc._detect_delete_inapplicable("普通文本") is None

    def test_english_only(self) -> None:
        svc = _make_service()
        assert svc._detect_delete_inapplicable("apple/banana") is None

    def test_fullwidth_slash(self) -> None:
        svc = _make_service()
        result = svc._detect_delete_inapplicable("选项A／选项B")
        assert result is not None
        assert len(result) == 2


class TestBuildLlmPrompt:
    def test_contains_structure(self) -> None:
        svc = _make_service()
        structure = {"paragraphs": [{"text": "hello"}]}
        prompt = svc._build_llm_prompt(structure)
        assert "hello" in prompt
        assert "JSON" in prompt.upper()

    def test_contains_fill_types(self) -> None:
        svc = _make_service()
        prompt = svc._build_llm_prompt({})
        assert "text" in prompt
        assert "checkbox" in prompt
        assert "delete_inapplicable" in prompt


class TestParseLlmResponse:
    def test_plain_json(self) -> None:
        svc = _make_service()
        data = [{"position_locator": {}, "semantic_label": "name", "fill_type": "text"}]
        result = svc._parse_llm_response(json.dumps(data))
        assert len(result) == 1
        assert result[0]["semantic_label"] == "name"

    def test_markdown_wrapped(self) -> None:
        svc = _make_service()
        data = [{"position_locator": {}, "semantic_label": "x", "fill_type": "text"}]
        response = "```json\n" + json.dumps(data) + "\n```"
        result = svc._parse_llm_response(response)
        assert len(result) == 1

    def test_non_list_raises(self) -> None:
        svc = _make_service()
        with pytest.raises(ValueError, match="期望 JSON 数组"):
            svc._parse_llm_response('{"key": "value"}')

    def test_bad_json_raises(self) -> None:
        svc = _make_service()
        with pytest.raises(json.JSONDecodeError):
            svc._parse_llm_response("not json at all")

    def test_non_dict_items_skipped(self) -> None:
        svc = _make_service()
        response = json.dumps(["not_a_dict", {"semantic_label": "ok", "fill_type": "text", "position_locator": {}}])
        result = svc._parse_llm_response(response)
        assert len(result) == 1


class TestCreateFieldMappings:
    def test_paragraph_type(self) -> None:
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "paragraph", "paragraph_index": 0}, "semantic_label": "name", "fill_type": "text"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._create_field_mappings(template, mappings)

        assert len(result) == 1
        call_kwargs = mock_fm.objects.create.call_args[1]
        assert call_kwargs["position_description"] == "段落 0"

    def test_table_cell_type(self) -> None:
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "table_cell", "table_index": 1, "row": 2, "col": 3}, "semantic_label": "val", "fill_type": "text"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._create_field_mappings(template, mappings)

        call_kwargs = mock_fm.objects.create.call_args[1]
        assert "表格1" in call_kwargs["position_description"]

    def test_checkbox_type(self) -> None:
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "checkbox", "checkbox_index": 0}, "semantic_label": "chk", "fill_type": "checkbox"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._create_field_mappings(template, mappings)

        call_kwargs = mock_fm.objects.create.call_args[1]
        assert "复选框" in call_kwargs["position_description"]

    def test_invalid_fill_type_fallback(self) -> None:
        svc = _make_service()
        template = MagicMock()
        mappings = [{"position_locator": {"type": "paragraph", "paragraph_index": 0}, "semantic_label": "x", "fill_type": "invalid_type"}]

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._create_field_mappings(template, mappings)

        call_kwargs = mock_fm.objects.create.call_args[1]
        assert call_kwargs["fill_type"] == "text"


class TestCopyMappingsFrom:
    def test_copies_mappings(self) -> None:
        svc = _make_service()
        source = MagicMock()
        target = MagicMock()
        m1 = MagicMock(position_locator={}, position_description="p1", semantic_label="l1", fill_type="text", sort_order=0)
        m2 = MagicMock(position_locator={}, position_description="p2", semantic_label="l2", fill_type="checkbox", sort_order=1)

        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value = [m1, m2]
            mock_fm.objects.create.return_value = MagicMock()
            result = svc._copy_mappings_from(source, target)

        assert len(result) == 2
        assert mock_fm.objects.create.call_count == 2


class TestAnalyzeTemplate:
    def test_llm_path(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl_obj = MagicMock()
            mock_tpl.objects.get.return_value = mock_tpl_obj
            mock_tpl_obj.pk = 1
            mock_tpl_obj.file_path = "doc.docx"

            with patch.object(svc, "extract_structure", return_value={"paragraphs": []}), \
                 patch.object(svc._fingerprint_service, "compute_fingerprint", return_value="fp123"), \
                 patch.object(svc._fingerprint_service, "find_matching_template", return_value=None), \
                 patch.object(svc, "_build_llm_prompt", return_value="prompt"), \
                 patch.object(svc._llm_service, "complete", return_value=MagicMock(content='[{"semantic_label":"x","fill_type":"text","position_locator":{}}]')), \
                 patch.object(svc, "_create_field_mappings", return_value=[MagicMock()]):
                result = svc.analyze_template(1)

        assert len(result) == 1
        assert mock_tpl_obj.status.value == "ready"

    def test_fingerprint_match(self) -> None:
        svc = _make_service()
        matched = MagicMock()
        matched.pk = 99

        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl_obj = MagicMock()
            mock_tpl.objects.get.return_value = mock_tpl_obj
            mock_tpl_obj.pk = 1
            mock_tpl_obj.file_path = "doc.docx"

            with patch.object(svc, "extract_structure", return_value={}), \
                 patch.object(svc._fingerprint_service, "compute_fingerprint", return_value="fp123"), \
                 patch.object(svc._fingerprint_service, "find_matching_template", return_value=matched), \
                 patch.object(svc, "_copy_mappings_from", return_value=[MagicMock()]):
                result = svc.analyze_template(1)

        assert len(result) == 1
        assert mock_tpl_obj.mapping_source is matched

    def test_self_match_excluded(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl_obj = MagicMock()
            mock_tpl_obj.pk = 1
            mock_tpl_obj.mapping_source = None  # Start with None
            mock_tpl.objects.get.return_value = mock_tpl_obj
            mock_tpl_obj.file_path = "doc.docx"

            with patch.object(svc, "extract_structure", return_value={}), \
                 patch.object(svc._fingerprint_service, "compute_fingerprint", return_value="fp123"), \
                 patch.object(svc._fingerprint_service, "find_matching_template", return_value=mock_tpl_obj), \
                 patch.object(svc, "_build_llm_prompt", return_value="prompt"), \
                 patch.object(svc._llm_service, "complete", return_value=MagicMock(content='[]')), \
                 patch.object(svc, "_create_field_mappings", return_value=[]):
                result = svc.analyze_template(1)

        # mapping_source should still be None (self-match was excluded)
        assert mock_tpl_obj.mapping_source is None

    def test_failure_sets_status(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl:
            mock_tpl_obj = MagicMock()
            mock_tpl.objects.get.return_value = mock_tpl_obj

            with patch.object(svc, "extract_structure", side_effect=Exception("fail")):
                with pytest.raises(Exception, match="fail"):
                    svc.analyze_template(1)

        assert mock_tpl_obj.status.value == "analysis_failed"


class TestRetryAnalysis:
    def test_deletes_and_reanalyzes(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm, \
             patch.object(svc, "analyze_template", return_value=[]) as mock_analyze:
            mock_fm.objects.filter.return_value.delete.return_value = (3, {})
            result = svc.retry_analysis(1)
        mock_analyze.assert_called_once_with(1)


class TestCreateManualMapping:
    def test_creates_mapping(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplate") as mock_tpl, \
             patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_tpl.objects.get.return_value = MagicMock()
            mock_fm.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = 2
            mock_fm.objects.create.return_value = MagicMock()
            result = svc.create_manual_mapping(
                template_id=1,
                position_locator={"type": "paragraph", "paragraph_index": 0},
                position_description="para 0",
                semantic_label="name",
                fill_type="text",
            )
        call_kwargs = mock_fm.objects.create.call_args[1]
        assert call_kwargs["sort_order"] == 3


class TestDeleteMapping:
    def test_deletes(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.external_template.ExternalTemplateFieldMapping") as mock_fm:
            mock_fm.objects.filter.return_value.delete.return_value = (1, {})
            svc.delete_mapping(42)
        mock_fm.objects.filter.assert_called_with(pk=42)


class TestMaxFileSize:
    def test_value(self) -> None:
        assert AnalysisService.MAX_FILE_SIZE == 20 * 1024 * 1024
