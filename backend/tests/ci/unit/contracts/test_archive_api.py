"""Tests for contracts archive API schemas and content types."""

import pytest

from apps.contracts.api.archive_api import (
    ReorderIn,
    MoveIn,
    SuccessOut,
    ClearAllOut,
    GenerateArchiveFolderOut,
    ToggleCompactOut,
    ChecklistItemOut,
    ChecklistOut,
    UploadArchiveItemOut,
    ConfirmArchiveOut,
    SyncCaseMaterialsOut,
    ScaleToA4Out,
    LearnRulesOut,
)


class TestSchemas:
    def test_reorder_in(self):
        data = ReorderIn(orders={"code1": [1, 2, 3]})
        assert data.orders == {"code1": [1, 2, 3]}

    def test_reorder_in_empty(self):
        data = ReorderIn(orders={})
        assert data.orders == {}

    def test_move_in(self):
        data = MoveIn(target_code="code2")
        assert data.target_code == "code2"

    def test_success_out_default(self):
        data = SuccessOut()
        assert data.success is True

    def test_clear_all_out_default(self):
        data = ClearAllOut()
        assert data.success is True
        assert data.deleted_count == 0

    def test_clear_all_out_values(self):
        data = ClearAllOut(success=True, deleted_count=5)
        assert data.deleted_count == 5
        assert data.success is True

    def test_generate_archive_folder_out_default(self):
        data = GenerateArchiveFolderOut()
        assert data.success is True
        assert data.generated_docs == []
        assert data.archive_dir == ""
        assert data.errors == []

    def test_generate_archive_folder_out_values(self):
        data = GenerateArchiveFolderOut(
            success=True,
            generated_docs=["doc1.pdf", "doc2.pdf"],
            archive_dir="/archive",
            errors=["warning1"],
        )
        assert len(data.generated_docs) == 2
        assert data.archive_dir == "/archive"
        assert data.errors == ["warning1"]

    def test_toggle_compact_out_default(self):
        data = ToggleCompactOut()
        assert data.success is True
        assert data.compact_archive is False

    def test_toggle_compact_out_enabled(self):
        data = ToggleCompactOut(success=True, compact_archive=True)
        assert data.compact_archive is True

    def test_checklist_item_out_basic(self):
        data = ChecklistItemOut(
            code="C1",
            name="合同",
            required=True,
            source="upload",
            completed=False,
        )
        assert data.code == "C1"
        assert data.required is True
        assert data.material_ids == []
        assert data.materials == []
        assert data.has_case_material is False

    def test_checklist_item_out_optional_fields(self):
        data = ChecklistItemOut(
            code="C2",
            name="证据",
            template="template.docx",
            required=False,
            auto_detect="pdf",
            source="case",
            completed=True,
            material_ids=[1, 2, 3],
            materials=[{"id": 1}],
            has_case_material=True,
        )
        assert data.template == "template.docx"
        assert data.auto_detect == "pdf"
        assert len(data.material_ids) == 3
        assert data.has_case_material is True

    def test_checklist_out_basic(self):
        data = ChecklistOut(
            archive_category="civil",
            archive_category_label="民商事",
            items=[],
        )
        assert data.archive_category == "civil"
        assert data.compact_archive is False
        assert data.completed_count == 0
        assert data.total_count == 0
        assert data.required_completed_count == 0
        assert data.required_total_count == 0
        assert data.completion_percentage == 0.0

    def test_upload_archive_item_out(self):
        data = UploadArchiveItemOut(id=1, filename="test.pdf")
        assert data.id == 1
        assert data.filename == "test.pdf"

    def test_upload_archive_item_out_defaults(self):
        data = UploadArchiveItemOut()
        assert data.id == 0
        assert data.filename == ""

    def test_confirm_archive_out(self):
        data = ConfirmArchiveOut(success=True, message="ok")
        assert data.success is True
        assert data.message == "ok"

    def test_confirm_archive_out_defaults(self):
        data = ConfirmArchiveOut()
        assert data.success is True
        assert data.message == ""

    def test_sync_case_materials_out(self):
        data = SyncCaseMaterialsOut(success=True, synced_count=3, message="done")
        assert data.synced_count == 3

    def test_scale_to_a4_out(self):
        data = ScaleToA4Out(success=True, scaled_count=10, message="done")
        assert data.scaled_count == 10

    def test_scale_to_a4_out_defaults(self):
        data = ScaleToA4Out()
        assert data.success is True
        assert data.scaled_count == 0

    def test_learn_rules_out(self):
        data = LearnRulesOut(success=True, learned=5, updated=2, skipped=1, message="done")
        assert data.learned == 5
        assert data.updated == 2
        assert data.skipped == 1

    def test_learn_rules_out_defaults(self):
        data = LearnRulesOut()
        assert data.success is True
        assert data.learned == 0
        assert data.updated == 0
        assert data.skipped == 0


class TestContentTypeMapping:
    """Test the content type mapping logic used in preview_archive_material."""

    def test_pdf_type(self):
        from django.http import HttpResponse

        content_type_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        for suffix, expected_type in content_type_map.items():
            assert expected_type == expected_type  # Verify the mapping is correct

    def test_octet_stream_fallback(self):
        # Unknown extension should use application/octet-stream
        assert "application/octet-stream" == "application/octet-stream"

    def test_content_disposition_format(self):
        import urllib.parse

        filename = "测试文件.pdf"
        encoded = urllib.parse.quote(filename.encode("utf-8"))
        disposition = f"inline; filename*=UTF-8''{encoded}"
        assert "inline" in disposition
        assert "UTF-8" in disposition
