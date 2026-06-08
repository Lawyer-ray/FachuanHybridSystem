"""Extended tests for contracts.admin.mixins.archive_mixin — success/error paths."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.contracts.admin.mixins.archive_mixin import ContractArchiveMixin


class TestContractArchiveMixinSuccessPaths:
    """Test the success paths of archive mixin methods."""

    def _make_mixin(self):
        mixin = ContractArchiveMixin()
        mixin.has_view_permission = MagicMock(return_value=True)
        mixin.has_change_permission = MagicMock(return_value=True)
        mixin.admin_site = MagicMock()
        mixin.model = MagicMock()
        return mixin

    def test_generate_archive_docs_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_contract = MagicMock()
            mock_contract.folder_binding.folder_path = "/some/path"
            mock_svc.return_value.query_service.get_contract_detail.return_value = mock_contract
            with patch("apps.contracts.models.folder_binding.ContractFolderBinding") as MockBinding:
                mock_contract.folder_binding = MagicMock()
                mock_contract.folder_binding.folder_path = "/some/path"
                with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                    mock_gen.return_value.generate_archive_folder.return_value = {
                        "success": True,
                        "generated_docs": ["doc1.pdf"],
                        "archive_dir": "/archive",
                        "errors": [],
                    }
                    result = mixin.generate_archive_docs_view(request, 1)
                    data = json.loads(result.content)
                    assert data["success"] is True

    def test_generate_archive_docs_service_failure(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_contract = MagicMock()
            mock_contract.folder_binding.folder_path = "/some/path"
            mock_svc.return_value.query_service.get_contract_detail.return_value = mock_contract
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.generate_archive_folder.return_value = {
                    "success": False,
                    "error": "生成失败",
                }
                result = mixin.generate_archive_docs_view(request, 1)
                assert result.status_code == 500

    def test_generate_archive_docs_no_binding(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_contract = MagicMock()
            mock_svc.return_value.query_service.get_contract_detail.return_value = mock_contract
            with patch("apps.contracts.models.folder_binding.ContractFolderBinding") as MockBinding:
                MockBinding.DoesNotExist = type("DoesNotExist", (Exception,), {})
                mock_contract.folder_binding = MagicMock()
                mock_contract.folder_binding.folder_path = None
                result = mixin.generate_archive_docs_view(request, 1)
                assert result.status_code == 400

    def test_generate_single_archive_doc_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.generate_single_archive_document.return_value = {
                    "template_subtype": "cover",
                    "filename": "test.pdf",
                    "material_id": 1,
                }
                result = mixin.generate_single_archive_doc_view(request, 1, "code")
                data = json.loads(result.content)
                assert data["success"] is True

    def test_generate_single_archive_doc_error(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.generate_single_archive_document.return_value = {
                    "error": "生成失败",
                }
                result = mixin.generate_single_archive_doc_view(request, 1, "code")
                data = json.loads(result.content)
                assert data["success"] is False

    def test_detect_supervision_card_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.SupervisionCardExtractor") as mock_extractor:
                mock_extractor.return_value.detect_and_extract.return_value = {
                    "found": True,
                    "page_number": 3,
                    "material_id": 10,
                }
                result = mixin.detect_supervision_card_view(request, 1)
                data = json.loads(result.content)
                assert data["success"] is True
                assert data["found"] is True

    def test_toggle_compact_archive_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_contract = MagicMock()
            mock_contract.compact_archive = False
            mock_svc.return_value.query_service.get_contract_detail.return_value = mock_contract
            result = mixin.toggle_compact_archive_view(request, 1)
            data = json.loads(result.content)
            assert data["success"] is True
            assert data["compact_archive"] is True

    def test_scale_to_a4_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.scale_pages_to_a4.return_value = {"success": True}
                result = mixin.scale_to_a4_view(request, 1)
                data = json.loads(result.content)
                assert data["success"] is True

    def test_sync_case_materials_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = b'{"archive_item_codes": ["code1"], "case_ids": [1]}'
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as mock_checklist:
                mock_checklist.return_value.sync_case_materials_to_archive.return_value = {
                    "synced": [{"code": "code1"}],
                    "skipped": [],
                    "errors": [],
                }
                result = mixin.sync_case_materials_view(request, 1)
                data = json.loads(result.content)
                assert data["success"] is True
                assert data["synced_count"] == 1

    def test_reset_and_resync_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = b'{"archive_item_codes": ["code1"]}'
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as mock_checklist:
                mock_checklist.return_value.reset_and_resync_case_materials.return_value = {
                    "deleted_count": 3,
                    "sync_result": {
                        "synced": [{"code": "code1"}],
                        "skipped": [],
                        "errors": [],
                    },
                }
                result = mixin.reset_and_resync_case_materials_view(request, 1)
                data = json.loads(result.content)
                assert data["success"] is True
                assert data["deleted_count"] == 3

    def test_case_material_match_map_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as mock_checklist:
                mock_checklist.return_value.get_case_material_match_map.return_value = {"code1": [1, 2]}
                result = mixin.case_material_match_map_view(request, 1)
                data = json.loads(result.content)
                assert data["success"] is True

    def test_reorder_archive_materials_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps({"orders": {"code1": [3, 1, 2]}}).encode()
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = 3
            result = mixin.reorder_archive_materials_view(request, 1)
            data = json.loads(result.content)
            assert data["success"] is True

    def test_move_archive_material_missing_params(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps({"material_id": 0, "target_code": ""}).encode()
        result = mixin.move_archive_material_view(request, 1)
        assert result.status_code == 400

    def test_move_archive_material_not_found(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps({"material_id": 999, "target_code": "code2"}).encode()
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            result = mixin.move_archive_material_view(request, 1)
            assert result.status_code == 404

    def test_move_archive_material_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps({"material_id": 1, "target_code": "code2"}).encode()
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_material = MagicMock()
            mock_material.archive_item_code = "code1"
            mock_model.objects.filter.return_value.first.return_value = mock_material
            mock_model.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = 5
            result = mixin.move_archive_material_view(request, 1)
            data = json.loads(result.content)
            assert data["success"] is True

    def test_upload_archive_item_no_file(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        request.FILES = {}
        result = mixin.upload_archive_item_view(request, 1, "code")
        assert result.status_code == 400

    def test_upload_archive_item_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        mock_file = MagicMock()
        request.FILES = {"file": mock_file}
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.wiring.build_archive_checklist_service") as mock_checklist:
                mock_material = MagicMock()
                mock_material.id = 10
                mock_material.original_filename = "test.pdf"
                mock_checklist.return_value.upload_material_to_archive_item.return_value = mock_material
                result = mixin.upload_archive_item_view(request, 1, "code")
                data = json.loads(result.content)
                assert data["success"] is True

    def test_delete_archive_material_not_found(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            result = mixin.delete_archive_material_view(request, 1, 999)
            assert result.status_code == 404

    def test_delete_archive_material_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_material = MagicMock()
            mock_material.file_path = None
            mock_model.objects.filter.return_value.first.return_value = mock_material
            result = mixin.delete_archive_material_view(request, 1, 1)
            data = json.loads(result.content)
            assert data["success"] is True

    def test_clear_all_archive_materials_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "POST"
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_material = MagicMock()
            mock_material.file_path = None
            mock_model.objects.filter.return_value = [mock_material]
            result = mixin.clear_all_archive_materials_view(request, 1)
            data = json.loads(result.content)
            assert data["success"] is True
            assert data["deleted_count"] == 1

    def test_preview_archive_material_not_found(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        with patch("apps.contracts.admin.mixins.archive_mixin.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            result = mixin.preview_archive_material_view(request, 1, 999)
            assert result.status_code == 404

    def test_download_archive_item_success(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.GET = {}
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.download_archive_item.return_value = {
                    "content": b"file content",
                    "content_type": "application/pdf",
                    "filename": "test.pdf",
                }
                result = mixin.download_archive_item_view(request, 1, "code")
                assert result.status_code == 200

    def test_download_archive_item_error(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.GET = {}
        with patch("apps.contracts.admin.mixins.archive_mixin._get_contract_admin_service") as mock_svc:
            mock_svc.return_value.query_service.get_contract_detail.return_value = MagicMock()
            with patch("apps.contracts.services.archive.ArchiveGenerationService") as mock_gen:
                mock_gen.return_value.download_archive_item.return_value = {
                    "error": "文件不存在",
                }
                result = mixin.download_archive_item_view(request, 1, "code")
                assert result.status_code == 404
