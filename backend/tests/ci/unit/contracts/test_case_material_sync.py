"""Tests for case_material_sync module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.checklist.case_material_sync import (
    _apply_initial_order_for_synced,
    _collect_matching_materials,
    _convert_to_pdf_if_needed,
    upload_material_to_archive_item,
)


class TestCollectMatchingMaterials:
    """同一 archive_item_code 命中多个案件时应聚合全部案件的材料。

    回归：旧实现只收集首个命中案件的材料，其余案件的材料静默消失。
    """

    def test_aggregates_materials_across_cases(self, db):
        case1 = SimpleNamespace(id=1, name="案件一")
        case2 = SimpleNamespace(id=2, name="案件二")
        cm1 = SimpleNamespace(id=101, type_name="起诉状", category="doc", case_id=1)
        cm2 = SimpleNamespace(id=102, type_name="起诉状", category="doc", case_id=2)

        with (
            patch(
                "apps.contracts.services.archive.checklist.case_material_sync.match_type_name_to_code",
                return_value="code_a",
            ) as mock_match,
            patch("apps.cases.models.CaseMaterial") as mock_cm_model,
        ):
            mock_cm_model.objects.filter.return_value.select_related.return_value.only.return_value = [cm1, cm2]
            result = _collect_matching_materials([case1, case2], {"code_a": ["起诉状"]}, {"code_a": {"code": "code_a"}})

        assert set(result.keys()) == {"code_a"}
        assert [cm.id for cm in result["code_a"]] == [101, 102]
        assert mock_match.call_count == 2

    def test_no_cases_returns_empty(self, db):
        with patch("apps.cases.models.CaseMaterial") as mock_cm_model:
            result = _collect_matching_materials([], {}, {})
        assert result == {}
        mock_cm_model.objects.filter.assert_not_called()

    def test_unmatched_material_excluded(self, db):
        case1 = SimpleNamespace(id=1, name="案件一")
        cm1 = SimpleNamespace(id=101, type_name="不相关材料", category="doc", case_id=1)

        with (
            patch(
                "apps.contracts.services.archive.checklist.case_material_sync.match_type_name_to_code",
                return_value=None,
            ),
            patch("apps.cases.models.CaseMaterial") as mock_cm_model,
        ):
            mock_cm_model.objects.filter.return_value.select_related.return_value.only.return_value = [cm1]
            result = _collect_matching_materials([case1], {"code_a": ["起诉状"]}, {"code_a": {"code": "code_a"}})

        assert result == {}


class TestApplyInitialOrderForSynced:
    def test_empty_synced(self):
        with patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial") as MockMaterial:
            # 空列表早退，不查询数据库
            assert _apply_initial_order_for_synced([]) is None
            MockMaterial.objects.filter.assert_not_called()

    def test_single_item_no_reorder(self, db):
        with patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial") as MockMaterial:
            # material_id 不存在时查不到材料，不做任何重排/保存
            MockMaterial.objects.filter.return_value = []
            result = _apply_initial_order_for_synced([{"material_id": 99999, "archive_item_code": "code"}])
            assert result is None
            MockMaterial.objects.filter.assert_called_once()


class TestUploadMaterialToArchiveItem:
    def test_invalid_code_raises(self, db):
        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1

        with pytest.raises(ValueError, match="无效的归档清单编号"):
            upload_material_to_archive_item(contract, "INVALID_CODE", MagicMock())

    @patch("apps.core.services.storage_service.save_uploaded_file")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    def test_valid_upload(self, mock_category, mock_model, mock_save, db):
        from apps.contracts.services.archive.checklist.case_material_sync import upload_material_to_archive_item

        mock_category.return_value = "litigation"

        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1

        mock_save.return_value = ("contracts/finalized/1/test.pdf", "test.pdf")
        mock_material = MagicMock()
        mock_material.id = 1
        mock_model.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_model.objects.create.return_value = mock_material

        uploaded_file = MagicMock()
        # Use a code that exists in the real ARCHIVE_CHECKLIST for 'litigation'
        # Let's check what codes exist
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST

        litigation_items = ARCHIVE_CHECKLIST.get("litigation", [])
        if not litigation_items:
            pytest.skip("No litigation checklist items found")
        test_code = litigation_items[0]["code"]

        result = upload_material_to_archive_item(contract, test_code, uploaded_file)
        assert result.id == 1


class TestGetCaseMaterialMatchMap:
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.CASE_MATERIAL_KEYWORD_MAPPING")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.ARCHIVE_CHECKLIST")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    def test_basic_match_map(self, mock_fm, mock_checklist, mock_kw, mock_category, db):
        from apps.contracts.services.archive.checklist.case_material_sync import get_case_material_match_map

        mock_category.return_value = "litigation"
        mock_kw.get.return_value = {}
        mock_checklist.get.return_value = []
        mock_fm.objects.filter.return_value.values_list.return_value = []

        contract = MagicMock()
        contract.case_type = "civil"
        contract.cases.all.return_value.only.return_value = []

        result = get_case_material_match_map(contract)
        assert "archive_category" in result
        assert "cases" in result
        assert "summary" in result


class TestResetAndResync:
    @patch("apps.contracts.services.archive.checklist.case_material_sync.get_archive_category")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.ARCHIVE_CHECKLIST")
    @patch("apps.contracts.services.archive.checklist.case_material_sync.FinalizedMaterial")
    def test_no_target_codes(self, mock_fm, mock_checklist, mock_category, db):
        from apps.contracts.services.archive.checklist.case_material_sync import reset_and_resync_case_materials

        mock_category.return_value = "litigation"
        mock_checklist.get.return_value = []

        contract = MagicMock()
        contract.case_type = "civil"

        result = reset_and_resync_case_materials(contract)
        assert result["deleted_count"] == 0


class TestConvertToPdfIfNeeded:
    """_convert_to_pdf_if_needed() 的单元测试。"""

    def test_pdf_passthrough(self, tmp_path):
        """PDF 文件不处理，原样返回。"""
        pdf = tmp_path / "contracts" / "finalized" / "1" / "abc.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4")

        with patch("django.conf.settings.MEDIA_ROOT", str(tmp_path)):
            rel, name = _convert_to_pdf_if_needed("contracts/finalized/1/abc.pdf", "材料.pdf", 1)
        assert rel == "contracts/finalized/1/abc.pdf"
        assert name == "材料.pdf"

    def test_docx_converts_to_pdf(self, tmp_path):
        """docx 文件转换成功后路径和文件名都更新为 .pdf。"""
        docx = tmp_path / "contracts" / "finalized" / "1" / "abc.docx"
        docx.parent.mkdir(parents=True)
        docx.write_bytes(b"PK\x03\x04")

        fake_pdf = tmp_path / "converted.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4")

        with (
            patch("django.conf.settings.MEDIA_ROOT", str(tmp_path)),
            patch(
                "apps.documents.services.infrastructure.pdf_merge_utils.resolve_material_to_temp_pdf",
                return_value=(fake_pdf, True),
            ),
        ):
            rel, name = _convert_to_pdf_if_needed("contracts/finalized/1/abc.docx", "起诉状.docx", 1)

        assert rel == "contracts/finalized/1/abc.pdf"
        assert name == "起诉状.pdf"
        # 原 docx 已被删除
        assert not docx.exists()
        # 新 PDF 已移到位
        assert (tmp_path / "contracts" / "finalized" / "1" / "abc.pdf").exists()

    def test_docx_failure_keeps_original(self, tmp_path):
        """转换失败时保留原文件。"""
        docx = tmp_path / "contracts" / "finalized" / "1" / "abc.docx"
        docx.parent.mkdir(parents=True)
        docx.write_bytes(b"PK\x03\x04")

        with (
            patch("django.conf.settings.MEDIA_ROOT", str(tmp_path)),
            patch(
                "apps.documents.services.infrastructure.pdf_merge_utils.resolve_material_to_temp_pdf",
                return_value=(None, False),
            ),
        ):
            rel, name = _convert_to_pdf_if_needed("contracts/finalized/1/abc.docx", "起诉状.docx", 1)

        assert rel == "contracts/finalized/1/abc.docx"
        assert name == "起诉状.docx"
        assert docx.exists()

    def test_xlsx_noop(self, tmp_path):
        """Excel 文件不处理。"""
        xlsx = tmp_path / "contracts" / "finalized" / "1" / "abc.xlsx"
        xlsx.parent.mkdir(parents=True)
        xlsx.write_bytes(b"PK\x03\x04")

        with patch("django.conf.settings.MEDIA_ROOT", str(tmp_path)):
            rel, name = _convert_to_pdf_if_needed("contracts/finalized/1/abc.xlsx", "表格.xlsx", 1)

        assert rel == "contracts/finalized/1/abc.xlsx"
        assert name == "表格.xlsx"
