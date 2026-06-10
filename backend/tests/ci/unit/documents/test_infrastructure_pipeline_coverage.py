"""
Tests for documents/services/infrastructure/ - pdf_utils, pipeline/packager, pipeline/preview, pipeline/renderer.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path as RealPath
from unittest.mock import MagicMock, patch

import pytest


class TestPdfUtils:
    def test_read_source_bytes_none_raises(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes

        with pytest.raises(ValueError, match="None"):
            _read_source_bytes(None)

    def test_read_source_bytes_raw(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes

        data = b"raw bytes"
        result = _read_source_bytes(data)
        assert result == b"raw bytes"

    def test_read_source_bytes_bytearray(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes

        data = bytearray(b"bytearray data")
        result = _read_source_bytes(data)
        assert isinstance(result, bytes)

    def test_read_source_bytes_path(self, tmp_path):
        from apps.core.utils.path import Path
        from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes

        f = tmp_path / "test.pdf"
        f.write_bytes(b"pdf content")
        result = _read_source_bytes(Path(str(f)))
        assert result == b"pdf content"

    def test_read_source_bytes_string_path(self, tmp_path):
        from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes

        f = tmp_path / "test.pdf"
        f.write_bytes(b"pdf content")
        result = _read_source_bytes(str(f))
        assert result == b"pdf content"

    def test_read_django_field_file(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_django_field_file

        mock_file = MagicMock()
        mock_file.open.return_value = None
        mock_file.read.return_value = b"field file data"
        mock_file.seek.return_value = None
        result = _read_django_field_file(mock_file)
        assert result == b"field file data"

    def test_read_django_field_file_no_open(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_django_field_file

        result = _read_django_field_file("not a file")
        assert result is None

    def test_read_file_like(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_file_like

        source = io.BytesIO(b"file like data")
        result = _read_file_like(source)
        assert result == b"file like data"

    def test_read_file_like_no_read(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_file_like

        result = _read_file_like(12345)
        assert result is None

    def test_read_from_path_attr(self, tmp_path):
        from apps.documents.services.infrastructure.pdf_utils import _read_from_path_attr

        f = tmp_path / "test.pdf"
        f.write_bytes(b"path attr data")
        mock_source = MagicMock()
        mock_source.path = str(f)
        result = _read_from_path_attr(mock_source)
        assert result == b"path attr data"

    def test_read_from_path_attr_no_path(self):
        from apps.documents.services.infrastructure.pdf_utils import _read_from_path_attr

        result = _read_from_path_attr("no path attr")
        assert result is None

    def test_get_pdf_page_count_with_error_pikepdf(self):
        from apps.documents.services.infrastructure.pdf_utils import get_pdf_page_count_with_error

        mock_pdf = MagicMock()
        mock_pdf.pages = [1, 2, 3]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = lambda s, *a: None

        with patch("pikepdf.open", return_value=mock_pdf):
            count, error = get_pdf_page_count_with_error(b"fake pdf")
            assert count == 3
            assert error is None

    def test_get_pdf_page_count_with_error_all_fail(self):
        from apps.documents.services.infrastructure.pdf_utils import get_pdf_page_count_with_error

        # Patch all three PDF libraries to fail
        with patch("pikepdf.open", side_effect=ValueError("bad pdf")):
            with patch("fitz.open", side_effect=ValueError("bad pdf")):
                with patch("pdfplumber.open", side_effect=ValueError("bad pdf")):
                    count, error = get_pdf_page_count_with_error(b"corrupt", default=5)
                    assert count == 5
                    assert error is not None

    def test_get_pdf_page_count_simple(self):
        from apps.documents.services.infrastructure.pdf_utils import get_pdf_page_count

        mock_pdf = MagicMock()
        mock_pdf.pages = [1, 2]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = lambda s, *a: None

        with patch("pikepdf.open", return_value=mock_pdf):
            count = get_pdf_page_count(b"fake pdf")
            assert count == 2


class TestZipPackager:
    def test_create_basic(self):
        from apps.documents.services.generation.pipeline.packager import ZipPackager

        packager = ZipPackager()
        structure = {"name": "root", "children": []}
        documents = [("", b"content", "file.txt")]
        result = packager.create(structure, documents)
        assert isinstance(result, bytes)
        assert len(result) > 0

        # Verify ZIP contents
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
            assert "root/file.txt" in names

    def test_create_with_subfolder(self):
        from apps.documents.services.generation.pipeline.packager import ZipPackager

        packager = ZipPackager()
        structure = {"name": "root", "children": [{"name": "sub", "children": []}]}
        documents = [("sub", b"data", "doc.docx")]
        result = packager.create(structure, documents)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "root/sub/doc.docx" in zf.namelist()

    def test_create_with_nested_folders(self):
        from apps.documents.services.generation.pipeline.packager import ZipPackager

        packager = ZipPackager()
        structure = {
            "name": "root",
            "children": [
                {"name": "a", "children": [{"name": "b", "children": []}]}
            ],
        }
        documents = [("", b"data", "readme.txt")]
        result = packager.create(structure, documents)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "root/a/" in zf.namelist()
            assert "root/a/b/" in zf.namelist()

    def test_create_empty_structure(self):
        from apps.documents.services.generation.pipeline.packager import ZipPackager

        packager = ZipPackager()
        structure = {}
        documents = [("", b"data", "f.txt")]
        result = packager.create(structure, documents)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "folder/f.txt" in zf.namelist()

    def test_create_multiple_documents(self):
        from apps.documents.services.generation.pipeline.packager import ZipPackager

        packager = ZipPackager()
        structure = {"name": "archive"}
        documents = [
            ("dir1", b"a", "a.txt"),
            ("dir2", b"b", "b.txt"),
        ]
        result = packager.create(structure, documents)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "archive/dir1/a.txt" in zf.namelist()
            assert "archive/dir2/b.txt" in zf.namelist()


class TestDocxRenderer:
    def test_render(self, tmp_path):
        from apps.documents.services.generation.pipeline.renderer import DocxRenderer

        # Create a minimal docx template
        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>",
            )
            zf.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>",
            )
            zf.writestr(
                "word/_rels/document.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                "</Relationships>",
            )
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        renderer = DocxRenderer()
        result = renderer.render(template_path, {"key": "value"})
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestDocxPreviewService:
    def test_preview_with_context(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        # Create a minimal docx with placeholders
        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{{ case_name }} and {{ defendant }}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        result = service.preview(template_path, {"case_name": "Test Case", "defendant": "John"})
        assert len(result) == 2
        assert any(r["key"] == "case_name" and r["value"] == "Test Case" for r in result)
        assert any(r["key"] == "defendant" and r["value"] == "John" for r in result)

    def test_preview_empty_context(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{{ var1 }}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        result = service.preview(template_path, {})
        assert len(result) == 1
        assert result[0]["status"] == "empty"

    def test_preview_with_rich_text_value(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{{ content }}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        mock_rich = MagicMock()
        mock_rich.plain_text = "Rich text content"
        result = service.preview(template_path, {"content": mock_rich})
        assert len(result) == 1
        assert result[0]["value"] == "Rich text content"

    def test_preview_with_list_value(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{{ items }}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        result = service.preview(template_path, {"items": [{"name": "A", "value": "1"}, "B"]})
        assert len(result) == 1
        assert "A" in result[0]["value"]

    def test_extract_ordered_vars(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{{ case_name }} {{r rich_var }}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        vars_list = service._extract_ordered_vars(template_path)
        assert "case_name" in vars_list
        assert "rich_var" in vars_list

    def test_extract_for_loop_vars(self, tmp_path):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService

        template_path = str(tmp_path / "template.docx")
        with zipfile.ZipFile(template_path, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>{%tr for item in items %}{{ item.name }}{% endfor %}</w:t></w:r></w:p></w:body>"
                "</w:document>",
            )

        service = DocxPreviewService()
        vars_list = service._extract_ordered_vars(template_path)
        assert "items" in vars_list
        assert "item" not in vars_list  # Iterator variable should be skipped
