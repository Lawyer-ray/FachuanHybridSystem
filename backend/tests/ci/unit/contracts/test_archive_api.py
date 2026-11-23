"""Tests for contracts archive API schemas and content types."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.contracts.api.archive_api import (
    ChecklistItemOut,
    ChecklistOut,
    ClearAllOut,
    ConfirmArchiveOut,
    GenerateArchiveFolderOut,
    LearnRulesOut,
    MoveIn,
    ReorderIn,
    ScaleToA4Out,
    SuccessOut,
    SyncCaseMaterialsOut,
    ToggleCompactOut,
    UploadArchiveItemOut,
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
    """归档材料下载的 后缀 → Content-Type 映射（直接调用生产函数）。

    S12-02（2026-11-23 二轮审计）：原实现在测试里另抄一份 `content_type_map`，
    再 `assert expected_type == expected_type` 自比（另一条是
    `"application/octet-stream" == "application/octet-stream"`）→ 零覆盖却显示通过。
    现在构造真实临时文件、patch 掉 media 路径解析后调生产
    `download_handler._read_material_file`，删掉生产分支即会红。
    """

    @staticmethod
    def _content_type(suffix: str, tmp_path) -> str:
        from typing import Any

        from apps.contracts.services.archive.generation.download_handler import _read_material_file

        probe = tmp_path / f"probe{suffix}"
        probe.write_bytes(b"archive-probe")
        # _read_material_file 只读 file_path / original_filename 两个属性
        material: Any = SimpleNamespace(file_path=f"archive/probe{suffix}", original_filename=f"probe{suffix}")

        with patch("apps.core.services.storage_service.to_media_abs", return_value=probe):
            payload = _read_material_file(material)

        assert payload["content"] == b"archive-probe"
        return str(payload["content_type"])

    def test_pdf_type(self, tmp_path):
        assert self._content_type(".pdf", tmp_path) == "application/pdf"

    def test_docx_type(self, tmp_path):
        assert (
            self._content_type(".docx", tmp_path)
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_octet_stream_fallback(self, tmp_path):
        # 未知后缀一律 application/octet-stream
        assert self._content_type(".zip", tmp_path) == "application/octet-stream"
